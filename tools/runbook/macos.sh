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

# ── Setup steps ───────────────────────────────────────────────────────────────
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

setup_infra() {
  step "Starting infrastructure"
  run docker compose -f "$SERVICES_DIR/docker-compose.yml" up -d
  poll_healthy "docker infra" \
    "! docker compose -f '$SERVICES_DIR/docker-compose.yml' ps --format '{{.Health}}' 2>/dev/null | grep -qE 'starting|unhealthy'" \
    60 || { fail "Check: docker compose -f $SERVICES_DIR/docker-compose.yml ps"; exit 1; }
}

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
  run bash -c "cat > '$tmp_dir/meta.json' << 'METAEOF'
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

# ── Subcommand implementations ────────────────────────────────────────────────
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

# Temporary stubs for Task 4 functions (will be replaced)
start_api()    { log "start_api: not yet implemented"; }
deploy_nomad() { log "deploy_nomad: not yet implemented"; }

cmd_test()     { echo "test not yet implemented"; }
cmd_teardown() { echo "teardown not yet implemented"; }
cmd_status()   { echo "status not yet implemented"; }

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
