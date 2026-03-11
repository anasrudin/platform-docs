#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# upload-minio.sh — Upload Firecracker snapshot artifacts to MinIO
#
# Usage:
#   ./upload-minio.sh [OPTIONS]
#
# Options:
#   --snapshot-dir DIR   Local snapshot directory (required)
#   --name          NAME Snapshot name used as MinIO path prefix (required)
#   --kernel        PATH Optional kernel binary to upload
#   --endpoint      URL  MinIO endpoint (default: $MINIO_ENDPOINT or localhost:9000)
#   --bucket        NAME MinIO bucket (default: platform-snapshots)
#   --dry-run            Print mc commands without executing
#
# Uploads:
#   platform-snapshots/<name>/vmstate.bin
#   platform-snapshots/<name>/memory.bin
#   platform-snapshots/<name>/rootfs.ext4   (if --kernel given)
#   platform-snapshots/<name>/kernel.bin    (if --kernel given)
#   platform-snapshots/<name>/meta.json
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SNAPSHOT_DIR=""
SNAPSHOT_NAME=""
KERNEL_PATH=""
ROOTFS_PATH=""
ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
BUCKET="platform-snapshots"
DRY_RUN=false
ALIAS="sb-upload-$$"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot-dir) SNAPSHOT_DIR="$2"; shift 2 ;;
    --name)         SNAPSHOT_NAME="$2"; shift 2 ;;
    --kernel)       KERNEL_PATH="$2"; shift 2 ;;
    --rootfs)       ROOTFS_PATH="$2"; shift 2 ;;
    --endpoint)     ENDPOINT="$2"; shift 2 ;;
    --bucket)       BUCKET="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=true; shift ;;
    --help)         grep '^#' "$0" | head -22 | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$SNAPSHOT_DIR" ]] && { echo "ERROR: --snapshot-dir required" >&2; exit 1; }
[[ -z "$SNAPSHOT_NAME" ]] && { echo "ERROR: --name required" >&2; exit 1; }
[[ ! -d "$SNAPSHOT_DIR" ]] && { echo "ERROR: $SNAPSHOT_DIR not found" >&2; exit 1; }

# Remap files to canonical MinIO names
STATE_FILE="$SNAPSHOT_DIR/state"
MEM_FILE="$SNAPSHOT_DIR/mem"
META_FILE="$SNAPSHOT_DIR/meta.json"

[[ ! -f "$STATE_FILE" ]] && { echo "ERROR: $STATE_FILE not found" >&2; exit 1; }
[[ ! -f "$MEM_FILE"   ]] && { echo "ERROR: $MEM_FILE not found" >&2; exit 1; }
[[ ! -f "$META_FILE"  ]] && { echo "ERROR: $META_FILE not found" >&2; exit 1; }

# ── Ensure mc is available ────────────────────────────────────────────────────
if ! command -v mc &>/dev/null; then
  ARCH="$(uname -m)"
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  MC_ARCH="$([[ $ARCH == 'aarch64' ]] && echo arm64 || echo amd64)"
  MC_URL="https://dl.min.io/client/mc/release/${OS}-${MC_ARCH}/mc"
  echo "Installing mc from $MC_URL..."
  curl -fsSL "$MC_URL" -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc
fi

# ── Helper wrappers ──────────────────────────────────────────────────────────
run_mc() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] mc $*"
  else
    mc "$@"
  fi
}

upload_file() {
  local src="$1"
  local dest_key="$2"
  local label="$3"
  local size
  size="$(du -sh "$src" 2>/dev/null | cut -f1 || echo "?")"
  echo "  Uploading $label ($size)..."
  run_mc cp "$src" "${ALIAS}/${BUCKET}/${SNAPSHOT_NAME}/${dest_key}"
}

echo "=== MinIO Snapshot Upload ==="
echo "  Endpoint:  $ENDPOINT"
echo "  Bucket:    $BUCKET"
echo "  Snapshot:  $SNAPSHOT_NAME"
echo "  Dir:       $SNAPSHOT_DIR"
echo ""

# ── Configure mc alias ────────────────────────────────────────────────────────
cleanup() { mc alias remove "$ALIAS" &>/dev/null || true; }
trap cleanup EXIT

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] mc alias set $ALIAS $ENDPOINT $ACCESS_KEY ****"
else
  mc alias set "$ALIAS" "$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" --quiet
fi

# ── Ensure bucket exists ──────────────────────────────────────────────────────
if [[ "$DRY_RUN" != "true" ]]; then
  mc ls "${ALIAS}/${BUCKET}" &>/dev/null || mc mb "${ALIAS}/${BUCKET}"
fi

# ── Upload snapshot files ─────────────────────────────────────────────────────
upload_file "$STATE_FILE" "vmstate.bin" "VM state"
upload_file "$MEM_FILE"   "memory.bin"  "Memory snapshot"
upload_file "$META_FILE"  "meta.json"   "Metadata"

[[ -n "$KERNEL_PATH" && -f "$KERNEL_PATH" ]] && \
  upload_file "$KERNEL_PATH" "kernel.bin" "Kernel"

[[ -n "$ROOTFS_PATH" && -f "$ROOTFS_PATH" ]] && \
  upload_file "$ROOTFS_PATH" "rootfs.ext4" "Rootfs"

# ── Verify ───────────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" != "true" ]]; then
  echo ""
  echo "Objects in ${BUCKET}/${SNAPSHOT_NAME}/:"
  mc ls "${ALIAS}/${BUCKET}/${SNAPSHOT_NAME}/"
fi

echo ""
echo "Upload complete: ${ENDPOINT}/${BUCKET}/${SNAPSHOT_NAME}/"
