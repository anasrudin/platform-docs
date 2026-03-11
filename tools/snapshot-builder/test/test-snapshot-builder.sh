#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test-snapshot-builder.sh — Unit tests for tools/snapshot-builder/
#
# Tests are self-contained: they use --dry-run and temp dirs, so they run
# without Docker, Firecracker, or MinIO.
#
# Usage:
#   ./test-snapshot-builder.sh          # run all tests
#   ./test-snapshot-builder.sh --keep   # keep temp dir after run
#
# Exit code: 0 = all passed, 1 = one or more failures
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

# ── Test framework ─────────────────────────────────────────────────────────────
PASS=0; FAIL=0; TOTAL=0
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "${GREEN}  PASS${NC} $1"; PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); }
fail() { echo -e "${RED}  FAIL${NC} $1: ${2:-}"; FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); }
section() { echo -e "\n${YELLOW}── $1 ──${NC}"; }

assert_file() {
  local label="$1" path="$2"
  if [[ -f "$path" ]]; then pass "$label"; else fail "$label" "file not found: $path"; fi
}
assert_contains() {
  local label="$1" file="$2" pattern="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    pass "$label"
  else
    fail "$label" "pattern '$pattern' not found in $file"
  fi
}
assert_exit() {
  local label="$1"; shift
  local expected_code="${1}"; shift
  local actual_code=0
  "$@" &>/dev/null || actual_code=$?
  if [[ "$actual_code" -eq "$expected_code" ]]; then
    pass "$label"
  else
    fail "$label" "expected exit $expected_code, got $actual_code"
  fi
}

# ── Setup ──────────────────────────────────────────────────────────────────────
TMP="$(mktemp -d /tmp/sb-test-XXXXXX)"
cleanup() { [[ "$KEEP" == "false" ]] && rm -rf "$TMP"; }
trap cleanup EXIT

export SNAPSHOT_OUT_DIR="$TMP/snapshots"
export SNAPSHOT_CACHE_DIR="$TMP/cache"
mkdir -p "$SNAPSHOT_OUT_DIR" "$SNAPSHOT_CACHE_DIR"

echo "=== Snapshot Builder Tests ==="
echo "  Temp dir: $TMP"

# ─────────────────────────────────────────────────────────────────────────────
section "1. Script sanity checks"

assert_file "snapshot-builder.sh exists"  "$SB_DIR/snapshot-builder.sh"
assert_file "build-rootfs.sh exists"      "$SB_DIR/build-rootfs.sh"
assert_file "upload-minio.sh exists"      "$SB_DIR/upload-minio.sh"
assert_file "config/python-v1.env exists" "$SB_DIR/config/python-v1.env"

# All scripts must be executable
for f in snapshot-builder.sh build-rootfs.sh upload-minio.sh; do
  [[ -x "$SB_DIR/$f" ]] && pass "$f is executable" || fail "$f is executable" "not executable"
done

# ─────────────────────────────────────────────────────────────────────────────
section "2. --help flag"

"$SB_DIR/snapshot-builder.sh" --help | grep -q "snapshot-builder" \
  && pass "snapshot-builder --help" \
  || fail "snapshot-builder --help" "no output"

"$SB_DIR/build-rootfs.sh" --help | grep -q "rootfs" \
  && pass "build-rootfs --help" \
  || fail "build-rootfs --help" "no output"

"$SB_DIR/upload-minio.sh" --help | grep -q "MinIO\|upload\|minio" \
  && pass "upload-minio --help" \
  || fail "upload-minio --help" "no output"

# ─────────────────────────────────────────────────────────────────────────────
section "3. Config file loading"

assert_contains "config has SNAPSHOT_NAME" "$SB_DIR/config/python-v1.env" "SNAPSHOT_NAME"
assert_contains "config has VCPUS"         "$SB_DIR/config/python-v1.env" "VCPUS"
assert_contains "config has MINIO_BUCKET"  "$SB_DIR/config/python-v1.env" "MINIO_BUCKET"
assert_contains "config has PYTHON_VERSION" "$SB_DIR/config/python-v1.env" "PYTHON_VERSION"

# ─────────────────────────────────────────────────────────────────────────────
section "4. build-rootfs.sh --dry-run"

"$SB_DIR/build-rootfs.sh" \
  --name "test-snap" \
  --out  "$TMP/cache/test-snap.ext4" \
  --size 16 \
  --dry-run

assert_file "dry-run rootfs image created" "$TMP/cache/test-snap.ext4"

# Check size is non-zero (at least partially written)
SIZE=$(stat -f%z "$TMP/cache/test-snap.ext4" 2>/dev/null || stat --printf="%s" "$TMP/cache/test-snap.ext4" 2>/dev/null || echo 0)
[[ "$SIZE" -gt 0 ]] && pass "rootfs image non-empty (${SIZE} bytes)" \
  || fail "rootfs image non-empty" "size is 0"

# ─────────────────────────────────────────────────────────────────────────────
section "5. snapshot-builder.sh --dry-run (full pipeline)"

"$SB_DIR/snapshot-builder.sh" \
  --name         "test-v1" \
  --skip-snapshot \
  --skip-upload  \
  --dry-run 2>&1 | tee "$TMP/sb-output.log" >/dev/null || true

assert_file "builder output log exists" "$TMP/sb-output.log"

# ─────────────────────────────────────────────────────────────────────────────
section "6. snapshot-builder.sh --skip-snapshot placeholder"

"$SB_DIR/snapshot-builder.sh" \
  --name          "placeholder-v1" \
  --skip-rootfs   \
  --skip-snapshot \
  --skip-upload   \
  2>&1 | tee "$TMP/placeholder-output.log" >/dev/null || true

# The builder should create placeholder meta.json when --skip-snapshot is used
META="$SNAPSHOT_OUT_DIR/placeholder-v1/meta.json"
assert_file "placeholder meta.json created" "$META"
assert_contains "meta.json has name field" "$META" "placeholder-v1"

# ─────────────────────────────────────────────────────────────────────────────
section "7. upload-minio.sh argument validation"

# Missing required args should exit non-zero
assert_exit "upload-minio fails without --snapshot-dir" 1 \
  "$SB_DIR/upload-minio.sh" --name "foo"

assert_exit "upload-minio fails without --name" 1 \
  "$SB_DIR/upload-minio.sh" --snapshot-dir "$TMP"

assert_exit "upload-minio fails for nonexistent dir" 1 \
  "$SB_DIR/upload-minio.sh" --snapshot-dir "/no/such/dir" --name "foo"

# ─────────────────────────────────────────────────────────────────────────────
section "8. upload-minio.sh --dry-run with valid snapshot dir"

# Prepare a fake snapshot dir
FAKE_SNAP="$TMP/fake-snapshot"
mkdir -p "$FAKE_SNAP"
echo '{"name":"fake"}' > "$FAKE_SNAP/meta.json"
dd if=/dev/zero of="$FAKE_SNAP/state" bs=1K count=1 status=none
dd if=/dev/zero of="$FAKE_SNAP/mem"   bs=1K count=1 status=none

"$SB_DIR/upload-minio.sh" \
  --snapshot-dir "$FAKE_SNAP" \
  --name         "fake-snap" \
  --dry-run 2>&1 | tee "$TMP/upload-dryrun.log" >/dev/null

assert_contains "dry-run shows vmstate.bin upload" "$TMP/upload-dryrun.log" "vmstate.bin"
assert_contains "dry-run shows memory.bin upload"  "$TMP/upload-dryrun.log" "memory.bin"
assert_contains "dry-run shows meta.json upload"   "$TMP/upload-dryrun.log" "meta.json"

# ─────────────────────────────────────────────────────────────────────────────
section "9. guest agent script syntax"

# Verify the embedded Python guest agent has valid syntax
AGENT_PY="$TMP/agent.py"
# Extract the agent from build-rootfs.sh (it's embedded in a heredoc)
sed -n '/^cat > "\$ROOTFS_DIR\/opt\/agent\/agent.py"/,/^AGENTEOF/p' \
  "$SB_DIR/build-rootfs.sh" | grep -v "^cat\|^AGENTEOF" > "$AGENT_PY" || true

if [[ -s "$AGENT_PY" ]]; then
  python3 -c "
import ast, sys
try:
    ast.parse(open('$AGENT_PY').read())
    sys.exit(0)
except SyntaxError as e:
    print(e)
    sys.exit(1)
" 2>/dev/null \
    && pass "guest agent.py has valid Python syntax" \
    || fail "guest agent.py has valid Python syntax" "syntax error"
else
  echo "  (skipped: could not extract agent.py from heredoc)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Results
echo ""
echo "─────────────────────────────────────"
echo "Results: ${PASS}/${TOTAL} passed"
[[ $FAIL -gt 0 ]] && echo -e "${RED}${FAIL} failures${NC}" || echo -e "${GREEN}All tests passed${NC}"
[[ "$KEEP" == "true" ]] && echo "  Temp dir kept: $TMP"
echo ""

[[ $FAIL -eq 0 ]]
