# Runbook Automation Scripts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/runbook/macos.sh` and `tools/runbook/linux.sh` — modular automation scripts (setup/test/teardown/status) for the Firecracker runbooks, with `mc` downloaded locally and no other system installs.

**Architecture:** Two standalone bash scripts (no shared library), each with a subcommand dispatcher and idempotent `setup`. State tracked in `tools/runbook/.state/` (gitignored). `mc` binary downloaded to `tools/runbook/bin/` on first run.

**Tech Stack:** bash 3.2+ (macOS compat), `set -euo pipefail`, `curl`, `jq`, `docker compose v2`, `nomad`, `uv`.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/runbook/.gitignore` | Create | Exclude `bin/` and `.state/` from git |
| `tools/runbook/macos.sh` | Create | Full macOS sim-mode automation script |
| `tools/runbook/linux.sh` | Create | Full Linux script — fc-agent real + platform-api sim |

---

## Task 1: Scaffold

**Files:**
- Create: `tools/runbook/.gitignore`
- Create: `tools/runbook/macos.sh` (skeleton)
- Create: `tools/runbook/linux.sh` (skeleton)

- [ ] **Step 1: Create .gitignore**

```
# tools/runbook/.gitignore
bin/
.state/
```

- [ ] **Step 2: Create macos.sh skeleton**

```bash
#!/usr/bin/env bash
# tools/runbook/macos.sh — Firecracker runbook automation (macOS sim mode)
# Usage: ./macos.sh <setup|test|teardown|status> [options]
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
  if [[ "$DRY_RUN" == "true" ]]; then echo "[dry-run] $*"; else "$@"; fi
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

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "$SUBCOMMAND" in
  setup)    cmd_setup    ;;
  test)     cmd_test     ;;
  teardown) cmd_teardown ;;
  status)   cmd_status   ;;
  *)
    echo "Usage: $0 <setup|test|teardown|status> [options]"
    echo "Options:"
    echo "  --snapshot-name NAME    (default: python-v1)"
    echo "  --minio-endpoint URL    (default: http://localhost:9000)"
    echo "  --api-url URL           (default: http://localhost:8080)"
    echo "  --no-nomad              Skip Nomad job"
    echo "  --dry-run               Print commands, do not execute"
    echo "  --purge                 teardown: also delete snapshot + venv"
    exit 1
    ;;
esac
```

- [ ] **Step 3: Create linux.sh skeleton** (identical to macos.sh skeleton — will diverge in later tasks)

Copy the same skeleton content to `tools/runbook/linux.sh`. Change only the comment on line 2:

```bash
# tools/runbook/linux.sh — Firecracker runbook automation (Linux — fc-agent real + platform-api sim)
```

- [ ] **Step 4: Make scripts executable**

```bash
chmod +x tools/runbook/macos.sh tools/runbook/linux.sh
```

- [ ] **Step 5: Verify syntax**

```bash
bash -n tools/runbook/macos.sh
bash -n tools/runbook/linux.sh
```

Expected: no output (syntax OK). If errors appear, fix them before proceeding.

- [ ] **Step 6: Commit**

```bash
git add tools/runbook/.gitignore tools/runbook/macos.sh tools/runbook/linux.sh
git commit -m "feat: scaffold runbook automation scripts"
```

---

## Task 2: Shared helper functions (macos.sh + linux.sh)

These functions are identical in both scripts. Add them above the `cmd_setup` stub in each file. Because the scripts are standalone (no shared lib), the functions are duplicated verbatim.

**Files:**
- Modify: `tools/runbook/macos.sh`
- Modify: `tools/runbook/linux.sh`

- [ ] **Step 1: Add `ensure_mc` to both scripts**

Insert after the `run()` function:

```bash
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
```

- [ ] **Step 2: Add `check_prereqs` to both scripts**

```bash
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
}
```

- [ ] **Step 3: Add `poll_healthy` to both scripts**

```bash
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
    if eval "$check_cmd" &>/dev/null 2>&1; then
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
```

- [ ] **Step 4: Verify syntax again**

```bash
bash -n tools/runbook/macos.sh
bash -n tools/runbook/linux.sh
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add tools/runbook/macos.sh tools/runbook/linux.sh
git commit -m "feat(runbook): add shared helpers — ensure_mc, check_prereqs, poll_healthy"
```

---

## Task 3: macos.sh — `cmd_setup` (infra, deps, snapshot)

**Files:**
- Modify: `tools/runbook/macos.sh`

Add these functions before the dispatch block, then call them in order from `cmd_setup`.

- [ ] **Step 1: Add `install_deps` function**

```bash
install_deps() {
  step "Installing Python dependencies"
  if [[ -f "$WORKER_DIR/.venv/bin/platform-api" ]]; then
    ok "platform-api already installed, skipping"
    return 0
  fi
  (
    cd "$WORKER_DIR"
    run uv venv .venv
    run uv pip install -e ".[dev]"
  )
  ok "Python deps installed"
}
```

- [ ] **Step 2: Add `setup_infra` function**

```bash
setup_infra() {
  step "Starting infrastructure"
  run docker compose -f "$SERVICES_DIR/docker-compose.yml" up -d
  poll_healthy "docker infra" \
    "! docker compose -f '$SERVICES_DIR/docker-compose.yml' ps --format '{{.Health}}' 2>/dev/null | grep -qE 'starting|unhealthy'" \
    60 || { fail "Check: docker compose -f $SERVICES_DIR/docker-compose.yml ps"; exit 1; }
}
```

- [ ] **Step 3: Add `upload_snapshot` function**

```bash
upload_snapshot() {
  step "Uploading snapshot to MinIO"

  # Configure mc alias (needed for existence check too)
  run "$MC" alias set sb-local "$MINIO_ENDPOINT" \
    "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --quiet

  # Idempotent: skip if already uploaded
  if [[ "$DRY_RUN" != "true" ]] && \
     "$MC" ls "sb-local/${MINIO_BUCKET}/${SNAPSHOT_NAME}/meta.json" &>/dev/null 2>&1; then
    ok "Snapshot $SNAPSHOT_NAME already in MinIO, skipping"
    return 0
  fi

  # Create temporary snapshot files
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp_dir'" RETURN

  # upload-minio.sh expects: state, mem, meta.json
  run bash -c "dd if=/dev/zero bs=1k count=4 2>/dev/null | gzip > '$tmp_dir/state'"
  run bash -c "dd if=/dev/zero bs=1k count=4 2>/dev/null | gzip > '$tmp_dir/mem'"
  run bash -c "cat > '$tmp_dir/meta.json' <<'METAEOF'
{
  \"name\": \"${SNAPSHOT_NAME}\",
  \"version\": \"3.12\",
  \"kernel\": \"vmlinux-5.10\",
  \"rootfs\": \"${SNAPSHOT_NAME}.ext4\",
  \"vcpus\": 2,
  \"mem_mib\": 512,
  \"dry_run\": true,
  \"files\": {}
}
METAEOF"

  # Delegate upload to existing script
  MINIO_ENDPOINT="$MINIO_ENDPOINT" \
  MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
  MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
  MINIO_BUCKET="$MINIO_BUCKET" \
  run "$TOOLS_DIR/snapshot-builder/upload-minio.sh" \
    --snapshot-dir "$tmp_dir" \
    --name "$SNAPSHOT_NAME"
  ok "Snapshot $SNAPSHOT_NAME uploaded"
}
```

- [ ] **Step 4: Add `cmd_setup` stub that calls all functions so far**

```bash
cmd_setup() {
  log "Setting up macOS sim-mode sandbox"
  mkdir -p "$STATE_DIR"
  check_prereqs
  ensure_mc
  install_deps
  setup_infra
  upload_snapshot
  start_api       # defined in Task 4
  deploy_nomad    # defined in Task 4
  echo "$SNAPSHOT_NAME" > "$STATE_DIR/snapshot-name"
  echo ""
  ok "Setup complete. Run: $0 test"
}
```

- [ ] **Step 5: Verify syntax**

```bash
bash -n tools/runbook/macos.sh
```

Expected: no output.

- [ ] **Step 6: Dry-run smoke test of setup**

```bash
cd /path/to/platform-docs
./tools/runbook/macos.sh setup --dry-run
```

Expected output contains lines like:
```
── Installing Python dependencies ──
── Starting infrastructure ──
[dry-run] docker compose -f .../services/docker-compose.yml up -d
── Uploading snapshot to MinIO ──
```

No errors, exits 0.

- [ ] **Step 7: Commit**

```bash
git add tools/runbook/macos.sh
git commit -m "feat(runbook/macos): setup — deps, infra, snapshot"
```

---

## Task 4: macos.sh — `start_api` and `deploy_nomad`

**Files:**
- Modify: `tools/runbook/macos.sh`

- [ ] **Step 1: Add `start_api` function**

```bash
start_api() {
  step "Starting platform-api"

  # Idempotent: skip if already running
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
```

- [ ] **Step 2: Add `deploy_nomad` function**

```bash
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
    warn "Start with: sudo nomad agent -dev -bind=0.0.0.0 -network-interface=lo0"
    warn "Skipping Nomad job deployment"
    return 0
  fi

  local job_name="sandbox-worker-macos"
  local venv_path="$WORKER_DIR/.venv"
  local job_file
  job_file="$(mktemp /tmp/sandbox-worker-macos-XXXXX.nomad)"
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
        FC_MODE            = "sim"
        FC_SNAPSHOT_BUCKET = "${SNAPSHOT_NAME}"
        SNAPSHOT_CACHE_DIR = "/tmp/sandbox-cache"
        MINIO_ENDPOINT     = "${MINIO_ENDPOINT}"
        MINIO_ACCESS_KEY   = "${MINIO_ACCESS_KEY}"
        MINIO_SECRET_KEY   = "${MINIO_SECRET_KEY}"
        MINIO_BUCKET       = "${MINIO_BUCKET}"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
EOF

  run nomad job run "$job_file"
  echo "$job_name" > "$STATE_DIR/nomad-job.txt"
  ok "Nomad job $job_name deployed"
}
```

- [ ] **Step 3: Verify syntax**

```bash
bash -n tools/runbook/macos.sh
```

Expected: no output.

- [ ] **Step 4: Dry-run full setup**

```bash
./tools/runbook/macos.sh setup --dry-run --no-nomad
```

Expected: all 6 setup steps print without error, exits 0.

- [ ] **Step 5: Commit**

```bash
git add tools/runbook/macos.sh
git commit -m "feat(runbook/macos): setup — start_api, deploy_nomad"
```

---

## Task 5: macos.sh — `cmd_test`, `cmd_teardown`, `cmd_status`

**Files:**
- Modify: `tools/runbook/macos.sh`

- [ ] **Step 1: Add `cmd_test` function**

```bash
cmd_test() {
  step "End-to-end test"

  # Guard: api must be healthy
  if ! curl -sf "${API_URL}/health" \
       | jq -e '.status=="healthy"' > /dev/null 2>&1; then
    fail "platform-api is not running. Run: $0 setup"
    exit 1
  fi

  # 1. Create session
  log "POST /sessions..."
  local session_resp session_id
  session_resp=$(curl -sf -X POST "${API_URL}/sessions" \
    -H "Content-Type: application/json" \
    -d '{"runtime":"microvm"}')
  session_id=$(echo "$session_resp" | jq -r '.session_id')
  ok "session_id: $session_id"

  # 2. Execute code
  log "POST /execute python_run..."
  local exec_resp status output
  exec_resp=$(curl -sf -X POST "${API_URL}/execute" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$session_id\",\"tool\":\"python_run\",\"input\":{\"code\":\"print('hello from sandbox')\"}}")
  status=$(echo "$exec_resp" | jq -r '.status')
  output=$(echo "$exec_resp" | jq -r '.output')

  # 3. Assert
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
```

- [ ] **Step 2: Add `cmd_teardown` function**

```bash
cmd_teardown() {
  step "Tearing down"

  # Stop platform-api
  if [[ -f "$STATE_DIR/api.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/api.pid")
    log "Stopping platform-api (pid=$pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    sleep 2
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

  # Stop infra
  log "Stopping docker compose..."
  run docker compose -f "$SERVICES_DIR/docker-compose.yml" down
  ok "Infrastructure stopped"

  # Clear state
  rm -rf "$STATE_DIR"
  ok "State cleared"

  # Purge (optional)
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
```

- [ ] **Step 3: Add `cmd_status` function**

```bash
cmd_status() {
  echo ""
  printf "${BOLD}%-22s %s${NC}\n" "Component" "Status"
  printf "%-22s %s\n" "──────────────────────" "──────────────────────────"

  # Docker infra
  local infra_status="stopped"
  if docker compose -f "$SERVICES_DIR/docker-compose.yml" ps -q 2>/dev/null \
       | grep -q .; then
    local n
    n=$(docker compose -f "$SERVICES_DIR/docker-compose.yml" ps -q 2>/dev/null \
        | wc -l | tr -d ' ')
    infra_status="running ($n containers)"
  fi
  printf "%-22s %s\n" "docker infra" "$infra_status"

  # platform-api
  local api_status="stopped"
  if [[ -f "$STATE_DIR/api.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/api.pid")
    if kill -0 "$pid" 2>/dev/null; then
      api_status="running  pid=$pid"
    else
      api_status="dead (stale pid=$pid)"
    fi
  fi
  printf "%-22s %s\n" "platform-api" "$api_status"

  # Nomad
  local nomad_status="not deployed"
  if [[ -f "$STATE_DIR/nomad-job.txt" ]]; then
    local job_name
    job_name=$(cat "$STATE_DIR/nomad-job.txt")
    if command -v nomad &>/dev/null \
       && nomad job status "$job_name" 2>/dev/null | grep -q "Status.*running"; then
      nomad_status="running ($job_name)"
    else
      nomad_status="stopped ($job_name)"
    fi
  fi
  printf "%-22s %s\n" "nomad job" "$nomad_status"

  # mc binary
  local mc_status="not downloaded"
  [[ -f "$MC" ]] && mc_status="cached"
  printf "%-22s %s\n" "mc binary" "$mc_status"
  echo ""
}
```

- [ ] **Step 4: Verify syntax**

```bash
bash -n tools/runbook/macos.sh
```

Expected: no output.

- [ ] **Step 5: Dry-run teardown**

```bash
./tools/runbook/macos.sh teardown --dry-run
```

Expected output:
```
── Tearing down ──
  platform-api not running
  Stopping docker compose...
[dry-run] docker compose -f .../services/docker-compose.yml down
  State cleared
  Teardown complete
```

- [ ] **Step 6: Commit**

```bash
git add tools/runbook/macos.sh
git commit -m "feat(runbook/macos): test, teardown, status subcommands"
```

---

## Task 6: linux.sh — Linux-specific changes

`linux.sh` starts as a copy of `macos.sh`. The steps below apply the Linux-specific differences on top.

**Files:**
- Modify: `tools/runbook/linux.sh`

- [ ] **Step 1: Copy macos.sh content into linux.sh**

Replace the content of `tools/runbook/linux.sh` entirely with the current content of `tools/runbook/macos.sh`, then change only the header comment on line 2:

```bash
# tools/runbook/linux.sh — Firecracker runbook automation (Linux — fc-agent real + platform-api sim)
```

- [ ] **Step 2: Replace `check_prereqs` with Linux version (add KVM + fc warnings)**

Find and replace the `check_prereqs` function:

```bash
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
```

- [ ] **Step 3: Replace `upload_snapshot` with Linux version (uses snapshot-builder.sh)**

Find and replace the `upload_snapshot` function:

```bash
upload_snapshot() {
  step "Building and uploading snapshot (dummy — real snapshot requires guest agent in rootfs)"
  warn "NOTE: platform-api runs in FC_MODE=sim because storage=None prevents real-mode startup."
  warn "      Real end-to-end VM execution requires a guest agent baked into the rootfs snapshot."
  warn "      See docs/how-to/firecracker-runbook-linux.md §7 for details."

  # Configure mc alias for existence check
  run "$MC" alias set sb-local "$MINIO_ENDPOINT" \
    "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --quiet

  if [[ "$DRY_RUN" != "true" ]] && \
     "$MC" ls "sb-local/${MINIO_BUCKET}/${SNAPSHOT_NAME}/meta.json" &>/dev/null 2>&1; then
    ok "Snapshot $SNAPSHOT_NAME already in MinIO, skipping"
    return 0
  fi

  # Use snapshot-builder.sh with --skip-rootfs --skip-snapshot to produce dummy files
  SNAPSHOT_OUT_DIR="/tmp/runbook-snapshots" \
  MINIO_ENDPOINT="$MINIO_ENDPOINT" \
  MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
  MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
  run "$TOOLS_DIR/snapshot-builder/snapshot-builder.sh" \
    --name "$SNAPSHOT_NAME" \
    --skip-rootfs \
    --skip-snapshot \
    --out-dir /tmp/runbook-snapshots

  ok "Snapshot $SNAPSHOT_NAME uploaded"
}
```

- [ ] **Step 4: Add `start_fc_agent` function (Linux-only)**

Insert after the `start_api` function:

```bash
start_fc_agent() {
  step "Starting fc-agent"

  # Idempotent
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
```

- [ ] **Step 5: Replace `cmd_setup` with Linux version (adds `start_fc_agent`)**

```bash
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
```

- [ ] **Step 6: Replace `cmd_teardown` with Linux version (stops fc-agent first)**

```bash
cmd_teardown() {
  step "Tearing down"

  # Stop fc-agent first
  if [[ -f "$STATE_DIR/fc-agent.pid" ]]; then
    local pid
    pid=$(cat "$STATE_DIR/fc-agent.pid")
    log "Stopping fc-agent (pid=$pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    sleep 2
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
    sleep 2
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
```

- [ ] **Step 7: Replace `cmd_status` with Linux version (adds fc-agent row)**

```bash
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

  # KVM advisory
  echo ""
  if [[ -r /dev/kvm ]]; then
    printf "  ${GREEN}/dev/kvm accessible${NC} — fc-agent can use real mode\n"
  else
    printf "  ${YELLOW}/dev/kvm not accessible${NC} — fc-agent uses sim mode\n"
  fi
  echo ""
}
```

- [ ] **Step 8: Verify syntax**

```bash
bash -n tools/runbook/linux.sh
```

Expected: no output.

- [ ] **Step 9: Dry-run linux.sh setup**

```bash
./tools/runbook/linux.sh setup --dry-run --no-nomad
```

Expected: all 7 setup steps print, including the fc-agent start step, exits 0.

- [ ] **Step 10: Commit**

```bash
git add tools/runbook/linux.sh
git commit -m "feat(runbook/linux): linux-specific setup — KVM check, snapshot-builder, fc-agent"
```

---

## Task 7: Integration smoke test

Run both scripts end-to-end with `--dry-run` to verify the complete flow, then do a real run of `macos.sh` (requires Docker running).

**Files:** none (verification only)

- [ ] **Step 1: Full dry-run of macos.sh**

```bash
cd /path/to/platform-docs
./tools/runbook/macos.sh setup    --dry-run --no-nomad
./tools/runbook/macos.sh test     --dry-run
./tools/runbook/macos.sh status
./tools/runbook/macos.sh teardown --dry-run --no-nomad
```

Expected for each: exits 0, all step headers print, no `[fail]` lines.

- [ ] **Step 2: Full dry-run of linux.sh**

```bash
./tools/runbook/linux.sh setup    --dry-run --no-nomad
./tools/runbook/linux.sh test     --dry-run
./tools/runbook/linux.sh status
./tools/runbook/linux.sh teardown --dry-run --no-nomad
```

Expected: same as above, with fc-agent step visible in setup/teardown, fc-agent row in status.

- [ ] **Step 3: Real run of macos.sh setup + test + teardown (requires Docker Desktop)**

```bash
# Terminal 1 — run setup
./tools/runbook/macos.sh setup --no-nomad

# Verify status
./tools/runbook/macos.sh status
```

Expected status output:
```
Component              Status
────────────────────── ──────────────────────────
docker infra           running (5 containers)
platform-api           running  pid=XXXXX
nomad job              not deployed
mc binary              cached
```

```bash
# Run test
./tools/runbook/macos.sh test
```

Expected:
```
── End-to-end test ──
  ✓ session_id: <uuid>
  ✓ PASS — status=completed, output contains 'hello from Python'
```

```bash
# Teardown
./tools/runbook/macos.sh teardown --no-nomad
```

Expected: all stopped, exits 0.

- [ ] **Step 4: Verify idempotence — run setup twice**

```bash
./tools/runbook/macos.sh setup --no-nomad
./tools/runbook/macos.sh setup --no-nomad   # second run
```

Expected: second run prints "already installed / already running / already in MinIO" for each step — no errors.

```bash
./tools/runbook/macos.sh teardown --no-nomad
```

- [ ] **Step 5: Final commit**

```bash
git add tools/runbook/macos.sh tools/runbook/linux.sh
git commit -m "feat(runbook): complete automation scripts — macos.sh and linux.sh"
```

---

## Self-Review

**Spec coverage:**
- ✅ `tools/runbook/macos.sh` with setup/test/teardown/status
- ✅ `tools/runbook/linux.sh` with setup/test/teardown/status
- ✅ `tools/runbook/.gitignore` excluding bin/ and .state/
- ✅ `mc` downloaded locally to `bin/mc`, never to system
- ✅ `check_prereqs` exits if python3/docker/uv/jq/curl missing
- ✅ `--no-nomad`, `--dry-run`, `--purge`, `--snapshot-name`, `--minio-endpoint`, `--api-url` options
- ✅ `setup` is idempotent (skips already-done steps)
- ✅ `teardown` uses `|| true` — never fails on missing PIDs
- ✅ `poll_healthy` used for infra, api, fc-agent
- ✅ linux.sh: KVM + firecracker warnings in check_prereqs
- ✅ linux.sh: snapshot-builder.sh with --skip-rootfs --skip-snapshot
- ✅ linux.sh: platform-api starts with FC_MODE=sim (not real)
- ✅ linux.sh: fc-agent started with FC_SNAPSHOT_BUCKET=snapshot_name
- ✅ linux.sh: fc-agent row in status table
- ✅ linux.sh: fc-agent stopped first in teardown
- ✅ State files: api.pid, fc-agent.pid, nomad-job.txt, snapshot-name

**Type consistency:** All function names match across tasks. `STATE_DIR`, `MC`, `WORKER_DIR`, `SERVICES_DIR`, `TOOLS_DIR` defined in Task 1 and used consistently throughout.
