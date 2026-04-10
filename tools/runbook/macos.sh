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

# ── Subcommand stubs (filled in later tasks) ──────────────────────────────────
cmd_setup()    { echo "setup not yet implemented"; }
cmd_test()     { echo "test not yet implemented"; }
cmd_teardown() { echo "teardown not yet implemented"; }
cmd_status()   { echo "status not yet implemented"; }

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
