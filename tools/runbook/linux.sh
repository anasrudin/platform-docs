#!/usr/bin/env bash
# tools/runbook/linux.sh — Firecracker runbook automation (Linux — fc-agent real + platform-api sim)
# Usage: ./linux.sh <setup|test|teardown|status> [options]
set -euo pipefail

RUNBOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$RUNBOOK_DIR/../.." && pwd)"
BIN_DIR="$RUNBOOK_DIR/bin"
STATE_DIR="$RUNBOOK_DIR/.state"
SERVICES_DIR="$REPO_ROOT/services"
WORKER_DIR="$REPO_ROOT/sandbox-worker"
TOOLS_DIR="$REPO_ROOT/tools"
MC="$BIN_DIR/mc"

# ── Defaults ──────────────────────────────────────────────────────────────────
SNAPSHOT_NAME="python-v1"
MINIO_ENDPOINT="http://localhost:9000"
MINIO_ACCESS_KEY="minioadmin"
MINIO_SECRET_KEY="minioadmin"
MINIO_BUCKET="platform-snapshots"
API_URL="http://localhost:8080"
NO_NOMAD=false
DRY_RUN=false
PURGE=false

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[runbook]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*" >&2; }
step() { echo -e "\n${BOLD}── $* ──${NC}"; }

run() {
  if [[ "$DRY_RUN" == "true" ]]; then printf '[dry-run]'; printf ' %q' "$@"; printf '\n'; else "$@"; fi
}

# ── mc download ───────────────────────────────────────────────────────────────
ensure_mc() {
  if [[ -f "$MC" ]]; then
    log "mc cached at $MC"
    return 0
  fi
  mkdir -p "$BIN_DIR"
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$arch" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64)  arch="amd64" ;;
    *) fail "Unsupported architecture: $arch"; exit 1 ;;
  esac
  local url="https://dl.min.io/client/mc/release/${os}-${arch}/mc"
  log "Downloading mc from $url..."
  run curl -fsSL "$url" -o "$MC"
  [[ "$DRY_RUN" != "true" ]] && chmod +x "$MC"
  ok "mc downloaded → $MC"
}

# ── Prerequisites ─────────────────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  local required=(python3 docker uv jq curl)
  [[ "$NO_NOMAD" == "false" ]] && required+=(nomad)
  for cmd in "${required[@]}"; do
    command -v "$cmd" &>/dev/null || missing+=("$cmd")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "Missing required tools: ${missing[*]}"
    fail "Install them and retry."
    exit 1
  fi
  ok "Prerequisites: ${required[*]}"

  # Linux-specific warnings (non-fatal)
  if ! command -v firecracker &>/dev/null; then
    warn "firecracker binary not found — fc-agent will use sim mode"
    warn "Install: see docs/how-to/firecracker-runbook-linux.md §1"
  fi
  if [[ ! -r /dev/kvm ]]; then
    warn "/dev/kvm not accessible — fc-agent will use sim mode (not real VMs)"
    warn "To enable: sudo usermod -aG kvm \$USER && newgrp kvm"
  else
    ok "/dev/kvm accessible — fc-agent can use real mode"
  fi
}

# ── Poll helper ───────────────────────────────────────────────────────────────
# poll_healthy LABEL CHECK_CMD [MAX_SECONDS]
# CHECK_CMD is evaluated with eval; returns 0 when ready.
poll_healthy() {
  local label="$1" check_cmd="$2" max_seconds="${3:-30}"
  if [[ "$DRY_RUN" == "true" ]]; then
    log "[dry-run] would poll: $label"
    return 0
  fi
  log "Waiting for $label (max ${max_seconds}s)..."
  local i=0 interval=2
  while (( i * interval < max_seconds )); do
    if eval "$check_cmd" &>/dev/null; then
      echo ""
      ok "$label is ready"
      return 0
    fi
    echo -n "."
    sleep "$interval"
    (( i++ )) || true
  done
  echo ""
  fail "$label not ready after ${max_seconds}s"
  return 1
}

# ── Argument parsing ──────────────────────────────────────────────────────────
SUBCOMMAND="${1:-}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot-name)  SNAPSHOT_NAME="$2";   shift 2 ;;
    --minio-endpoint) MINIO_ENDPOINT="$2";  shift 2 ;;
    --api-url)        API_URL="$2";         shift 2 ;;
    --no-nomad)       NO_NOMAD=true;        shift   ;;
    --dry-run)        DRY_RUN=true;         shift   ;;
    --purge)          PURGE=true;           shift   ;;
    *) fail "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Setup helpers ─────────────────────────────────────────────────────────────
install_deps() {
  step "Installing Python dependencies"
  if [[ -f "$WORKER_DIR/.venv/bin/platform-api" ]]; then
    ok "platform-api already installed, skipping"
    return 0
  fi
  (
    cd "$WORKER_DIR"
    run uv venv .venv --python 3.12
    run uv pip install -e ".[dev]"
  )
  ok "Python deps installed"
}

setup_infra() {
  step "Starting infrastructure"
  run docker compose -f "$SERVICES_DIR/docker-compose.yml" up -d
  poll_healthy "docker infra" \
    "docker compose -f '$SERVICES_DIR/docker-compose.yml' ps --format '{{.Health}}' 2>/dev/null | grep -q 'healthy'" \
    60 || { fail "Check: docker compose -f $SERVICES_DIR/docker-compose.yml ps"; exit 1; }
}

upload_snapshot() {
  step "Building and uploading snapshot"
  warn "NOTE: platform-api runs in FC_MODE=sim — storage=None prevents real-mode startup."
  warn "      Real VM execution requires a guest agent in the rootfs snapshot."
  warn "      See docs/how-to/firecracker-runbook-linux.md §7 for details."

  # Configure mc alias (needed for existence check too)
  run "$MC" alias set sb-local "$MINIO_ENDPOINT" \
    "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --quiet

  # Idempotent: skip if already uploaded
  if [[ "$DRY_RUN" != "true" ]] && \
     "$MC" ls "sb-local/${MINIO_BUCKET}/${SNAPSHOT_NAME}/meta.json" &>/dev/null 2>&1; then
    ok "Snapshot $SNAPSHOT_NAME already in MinIO, skipping"
    return 0
  fi

  # Use snapshot-builder.sh with --skip-rootfs --skip-snapshot for dummy snapshot
  PATH="$BIN_DIR:$PATH" \
  SNAPSHOT_OUT_DIR="/tmp/runbook-snapshots" \
  MINIO_ENDPOINT="$MINIO_ENDPOINT" \
  MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
  MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
  MINIO_BUCKET="$MINIO_BUCKET" \
  run "$TOOLS_DIR/snapshot-builder/snapshot-builder.sh" \
    --name "$SNAPSHOT_NAME" \
    --skip-rootfs \
    --skip-snapshot \
    --out-dir /tmp/runbook-snapshots

  ok "Snapshot $SNAPSHOT_NAME uploaded"
}

start_api() {
  step "Starting platform-api"

  if [[ -f "$STATE_DIR/api.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/api.pid")
    if kill -0 "$pid" 2>/dev/null; then
      ok "platform-api already running (pid=$pid)"
      return 0
    fi
    warn "Stale PID $pid found, restarting..."
    rm -f "$STATE_DIR/api.pid"
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    log "[dry-run] would start platform-api (FC_MODE=sim)"
    return 0
  fi

  local log_file="$STATE_DIR/api.log"
  FC_MODE=sim \
  MINIO_ENDPOINT="$MINIO_ENDPOINT" \
  MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
  MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
    "$WORKER_DIR/.venv/bin/platform-api" \
    > "$log_file" 2>&1 &
  local pid=$!
  echo "$pid" > "$STATE_DIR/api.pid"
  log "platform-api started (pid=$pid), waiting for health..."

  poll_healthy "platform-api /health" \
    "curl -sf '${API_URL}/health' | jq -e '.status==\"healthy\"' > /dev/null" \
    30 || {
      fail "platform-api did not become healthy. Logs:"
      tail -20 "$log_file" >&2
      exit 1
    }
}

start_fc_agent() {
  step "Starting fc-agent"

  if [[ -f "$STATE_DIR/fc-agent.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/fc-agent.pid")
    if kill -0 "$pid" 2>/dev/null; then
      ok "fc-agent already running (pid=$pid)"
      return 0
    fi
    warn "Stale fc-agent PID $pid, restarting..."
    rm -f "$STATE_DIR/fc-agent.pid"
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    log "[dry-run] would start fc-agent (FC_MODE auto-detects /dev/kvm)"
    return 0
  fi

  local log_file="$STATE_DIR/fc-agent.log"
  FC_SNAPSHOT_BUCKET="$SNAPSHOT_NAME" \
  MINIO_ENDPOINT="$MINIO_ENDPOINT" \
  MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
  MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
  MINIO_BUCKET="$MINIO_BUCKET" \
  SNAPSHOT_CACHE_DIR="/tmp/sandbox-cache" \
    "$WORKER_DIR/.venv/bin/fc-agent" \
    > "$log_file" 2>&1 &
  local pid=$!
  echo "$pid" > "$STATE_DIR/fc-agent.pid"
  log "fc-agent started (pid=$pid), waiting for health..."

  poll_healthy "fc-agent /health" \
    "curl -sf 'http://localhost:8081/health' | jq -e '.status==\"healthy\"' > /dev/null" \
    30 || {
      fail "fc-agent did not become healthy. Logs:"
      tail -20 "$log_file" >&2
      exit 1
    }
}

deploy_nomad() {
  step "Deploying Nomad job"

  if [[ "$NO_NOMAD" == "true" ]]; then
    log "Skipping Nomad job (--no-nomad)"
    return 0
  fi

  if ! command -v nomad &>/dev/null; then
    warn "nomad not in PATH — skipping job deployment"
    return 0
  fi

  if ! nomad node status &>/dev/null 2>&1; then
    warn "Nomad agent not running."
    warn "Start with: sudo nomad agent -dev -bind=0.0.0.0 -network-interface=eth0"
    warn "Skipping Nomad job deployment"
    return 0
  fi

  local job_name="sandbox-worker-linux"
  local venv_path="$WORKER_DIR/.venv"
  local job_file
  job_file="$(mktemp /tmp/sandbox-worker-linux-XXXXX.nomad)"
  # shellcheck disable=SC2064
  trap "rm -f '$job_file'" RETURN

  cat > "$job_file" <<EOF
job "$job_name" {
  datacenters = ["dc1"]
  type        = "service"

  group "fc-agent" {
    count = 1

    task "fc-agent" {
      driver = "raw_exec"

      config {
        command = "${venv_path}/bin/fc-agent"
      }

      env {
        FC_SNAPSHOT_BUCKET = "${SNAPSHOT_NAME}"
        SNAPSHOT_CACHE_DIR = "/tmp/sandbox-cache"
        MINIO_ENDPOINT     = "${MINIO_ENDPOINT}"
        MINIO_ACCESS_KEY   = "${MINIO_ACCESS_KEY}"
        MINIO_SECRET_KEY   = "${MINIO_SECRET_KEY}"
        MINIO_BUCKET       = "${MINIO_BUCKET}"
      }

      resources {
        cpu    = 2000
        memory = 4096
      }
    }
  }
}
EOF

  run nomad job run "$job_file"
  echo "$job_name" > "$STATE_DIR/nomad-job.txt"
  ok "Nomad job $job_name deployed"
}

# ── Subcommand implementations ────────────────────────────────────────────────
cmd_setup() {
  log "Setting up Linux sandbox (fc-agent real + platform-api sim)"
  mkdir -p "$STATE_DIR"
  check_prereqs
  ensure_mc
  install_deps
  setup_infra
  upload_snapshot
  start_api
  start_fc_agent
  deploy_nomad
  echo "$SNAPSHOT_NAME" > "$STATE_DIR/snapshot-name"
  echo ""
  ok "Setup complete. Run: $0 test"
}

cmd_test() {
  [[ -f "$STATE_DIR/snapshot-name" ]] && SNAPSHOT_NAME="$(cat "$STATE_DIR/snapshot-name")"
  step "End-to-end test"

  if ! curl -sf "${API_URL}/health" \
       | jq -e '.status=="healthy"' > /dev/null 2>&1; then
    fail "platform-api is not running. Run: $0 setup"
    exit 1
  fi

  log "POST /sessions..."
  local session_resp session_id
  session_resp=$(curl -sf -X POST "${API_URL}/sessions" \
    -H "Content-Type: application/json" \
    -d '{"runtime":"microvm"}')
  session_id=$(echo "$session_resp" | jq -r '.session_id')
  ok "session_id: $session_id"

  log "POST /execute python_run..."
  local exec_resp status output
  exec_resp=$(curl -sf -X POST "${API_URL}/execute" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$session_id\",\"tool\":\"python_run\",\"input\":{\"code\":\"print('hello from sandbox')\"}}")
  status=$(echo "$exec_resp" | jq -r '.status')
  output=$(echo "$exec_resp" | jq -r '.output')

  local passed=true
  [[ "$status" != "completed" ]] && {
    fail "Expected status=completed, got: $status"; passed=false; }
  echo "$output" | grep -q "hello from Python" || {
    fail "Expected output to contain 'hello from Python'"; passed=false; }

  if [[ "$passed" == "true" ]]; then
    echo ""
    ok "PASS — status=completed, output contains 'hello from Python'"
    echo ""
    echo "$exec_resp" | jq
  else
    echo ""
    fail "FAIL — full response:"
    echo "$exec_resp" | jq >&2
    exit 1
  fi
}

cmd_teardown() {
  [[ -f "$STATE_DIR/snapshot-name" ]] && SNAPSHOT_NAME="$(cat "$STATE_DIR/snapshot-name")"
  step "Tearing down"

  # Stop fc-agent first
  if [[ -f "$STATE_DIR/fc-agent.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/fc-agent.pid")
    log "Stopping fc-agent (pid=$pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    sleep 5
    kill -KILL "$pid" 2>/dev/null || true
    rm -f "$STATE_DIR/fc-agent.pid"
    ok "fc-agent stopped"
  else
    log "fc-agent not running"
  fi

  # Stop platform-api
  if [[ -f "$STATE_DIR/api.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/api.pid")
    log "Stopping platform-api (pid=$pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    sleep 5
    kill -KILL "$pid" 2>/dev/null || true
    rm -f "$STATE_DIR/api.pid"
    ok "platform-api stopped"
  else
    log "platform-api not running"
  fi

  # Stop Nomad job
  if [[ "$NO_NOMAD" == "false" && -f "$STATE_DIR/nomad-job.txt" ]]; then
    local job_name
    job_name=$(cat "$STATE_DIR/nomad-job.txt")
    log "Stopping Nomad job $job_name..."
    nomad job stop "$job_name" 2>/dev/null || true
    rm -f "$STATE_DIR/nomad-job.txt"
    ok "Nomad job stopped"
  fi

  log "Stopping docker compose..."
  run docker compose -f "$SERVICES_DIR/docker-compose.yml" down
  ok "Infrastructure stopped"

  rm -rf "$STATE_DIR"
  ok "State cleared"

  if [[ "$PURGE" == "true" ]]; then
    log "Purging MinIO snapshot $SNAPSHOT_NAME..."
    [[ -f "$MC" ]] && run "$MC" rm --recursive --force \
      "sb-local/${MINIO_BUCKET}/${SNAPSHOT_NAME}" 2>/dev/null || true
    log "Removing venv..."
    run rm -rf "$WORKER_DIR/.venv"
    ok "Purge complete"
  fi

  ok "Teardown complete"
}

cmd_status() {
  echo ""
  printf "${BOLD}%-22s %s${NC}\n" "Component" "Status"
  printf "%-22s %s\n" "──────────────────────" "──────────────────────────"

  local infra_status="stopped"
  if docker compose -f "$SERVICES_DIR/docker-compose.yml" ps -q 2>/dev/null \
       | grep -q .; then
    local n
    n=$(docker compose -f "$SERVICES_DIR/docker-compose.yml" ps -q 2>/dev/null \
        | wc -l | tr -d ' ')
    infra_status="running ($n containers)"
  fi
  printf "%-22s %s\n" "docker infra" "$infra_status"

  local api_status="stopped"
  if [[ -f "$STATE_DIR/api.pid" ]]; then
    local pid; pid=$(cat "$STATE_DIR/api.pid")
    kill -0 "$pid" 2>/dev/null \
      && api_status="running  pid=$pid" \
      || api_status="dead (stale pid=$pid)"
  fi
  printf "%-22s %s\n" "platform-api (sim)" "$api_status"

  local fc_status="stopped"
  if [[ -f "$STATE_DIR/fc-agent.pid" ]]; then
    local pid; pid=$(cat "$STATE_DIR/fc-agent.pid")
    kill -0 "$pid" 2>/dev/null \
      && fc_status="running  pid=$pid" \
      || fc_status="dead (stale pid=$pid)"
  fi
  printf "%-22s %s\n" "fc-agent" "$fc_status"

  local nomad_status="not deployed"
  if [[ -f "$STATE_DIR/nomad-job.txt" ]]; then
    local job_name; job_name=$(cat "$STATE_DIR/nomad-job.txt")
    command -v nomad &>/dev/null \
      && nomad job status "$job_name" 2>/dev/null | grep -q "Status.*running" \
      && nomad_status="running ($job_name)" \
      || nomad_status="stopped ($job_name)"
  fi
  printf "%-22s %s\n" "nomad job" "$nomad_status"

  local mc_status="not downloaded"
  [[ -f "$MC" ]] && mc_status="cached"
  printf "%-22s %s\n" "mc binary" "$mc_status"

  echo ""
  if [[ -r /dev/kvm ]]; then
    printf "  ${GREEN}/dev/kvm accessible${NC} — fc-agent can use real mode\n"
  else
    printf "  ${YELLOW}/dev/kvm not accessible${NC} — fc-agent uses sim mode\n"
  fi
  echo ""
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "$SUBCOMMAND" in
  setup)    cmd_setup    ;;
  test)     cmd_test     ;;
  teardown) cmd_teardown ;;
  status)   cmd_status   ;;
  ""|--help|-h)
    echo "Usage: $0 <setup|test|teardown|status> [options]"
    echo "Options:"
    echo "  --snapshot-name NAME    (default: python-v1)"
    echo "  --minio-endpoint URL    (default: http://localhost:9000)"
    echo "  --api-url URL           (default: http://localhost:8080)"
    echo "  --no-nomad              Skip Nomad job"
    echo "  --dry-run               Print commands, do not execute"
    echo "  --purge                 teardown: also delete snapshot + venv"
    exit 0
    ;;
  *)
    fail "Unknown subcommand: $SUBCOMMAND"
    echo "Run '$0 --help' for usage." >&2
    exit 1
    ;;
esac
