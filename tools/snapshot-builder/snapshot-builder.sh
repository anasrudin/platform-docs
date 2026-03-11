#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# snapshot-builder.sh — Build a Firecracker VM snapshot and upload to MinIO
#
# This is the main orchestrator.  It calls:
#   1. build-rootfs.sh   — creates a Python ext4 rootfs via Docker
#   2. build-snapshot.sh — boots the VM and captures a snapshot (Linux + KVM)
#   3. upload-minio.sh   — uploads artifacts to MinIO platform-snapshots bucket
#
# Usage:
#   ./snapshot-builder.sh [--config FILE] [OPTIONS]
#
# Options:
#   --config   FILE    Load variables from a .env file (default: config/python-v1.env)
#   --name     NAME    Snapshot name (overrides config)
#   --kernel   PATH    Path to vmlinux kernel binary (required unless --download-kernel)
#   --download-kernel  Download the Firecracker test kernel automatically
#   --skip-rootfs      Skip rootfs build (use existing rootfs.ext4 in cache dir)
#   --skip-snapshot    Skip Firecracker snapshot (useful when no KVM)
#   --skip-upload      Skip MinIO upload
#   --dry-run          Dry-run all subcommands
#   --out-dir  DIR     Local output dir (default: /var/sandbox/snapshots)
#   --help             Print this help
#
# Environment variables (override config):
#   MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
#   SNAPSHOT_OUT_DIR, SNAPSHOT_CACHE_DIR
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
CONFIG_FILE="$SCRIPT_DIR/config/python-v1.env"
SNAPSHOT_NAME=""          # set after config load
KERNEL_PATH=""
DOWNLOAD_KERNEL=false
SKIP_ROOTFS=false
SKIP_SNAPSHOT=false
SKIP_UPLOAD=false
DRY_RUN=false
OUT_DIR="${SNAPSHOT_OUT_DIR:-/var/sandbox/snapshots}"
CACHE_DIR="${SNAPSHOT_CACHE_DIR:-/var/sandbox/cache}"
VCPUS=2
MEM_MIB=512
PYTHON_VERSION="3.11"
ROOTFS_SIZE_MB=1024

# ── First pass: extract --config and --help only ──────────────────────────────
_ARGS=("$@")
for (( _i=0; _i<${#_ARGS[@]}; _i++ )); do
  case "${_ARGS[$_i]}" in
    --config) CONFIG_FILE="${_ARGS[$((_i+1))]}"; _i=$((_i+1)) ;;
    --help)   grep '^#' "$0" | head -28 | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
done

# ── Load config file (before CLI args so CLI overrides config) ────────────────
if [[ -f "$CONFIG_FILE" ]]; then
  echo "Loading config: $CONFIG_FILE"
  # shellcheck source=/dev/null
  set -a; source "$CONFIG_FILE"; set +a
fi

# ── Second pass: CLI args override config values ──────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)          shift 2 ;;                          # already handled
    --name)            SNAPSHOT_NAME="$2"; shift 2 ;;
    --kernel)          KERNEL_PATH="$2"; shift 2 ;;
    --download-kernel) DOWNLOAD_KERNEL=true; shift ;;
    --skip-rootfs)     SKIP_ROOTFS=true; shift ;;
    --skip-snapshot)   SKIP_SNAPSHOT=true; shift ;;
    --skip-upload)     SKIP_UPLOAD=true; shift ;;
    --dry-run)         DRY_RUN=true; shift ;;
    --out-dir)         OUT_DIR="$2"; shift 2 ;;
    --help)            grep '^#' "$0" | head -28 | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Fallback defaults after config + CLI
SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"

# ── Derived paths ─────────────────────────────────────────────────────────────
mkdir -p "$OUT_DIR" "$CACHE_DIR"
ROOTFS_PATH="$CACHE_DIR/${SNAPSHOT_NAME}.ext4"
SNAP_DIR="$OUT_DIR/$SNAPSHOT_NAME"
DR_FLAG="$([[ "$DRY_RUN" == true ]] && echo '--dry-run' || echo '')"

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Firecracker Snapshot Builder                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Snapshot:  $SNAPSHOT_NAME"
echo "  vCPUs:     $VCPUS"
echo "  Memory:    ${MEM_MIB}MiB"
echo "  Cache dir: $CACHE_DIR"
echo "  Out dir:   $OUT_DIR"
echo ""

# ── Step 1: Download kernel ───────────────────────────────────────────────────
if [[ "$DOWNLOAD_KERNEL" == "true" && -z "$KERNEL_PATH" ]]; then
  KERNEL_URL="${KERNEL_URL:-https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.10/x86_64/vmlinux-5.10.225}"
  KERNEL_PATH="$CACHE_DIR/vmlinux"
  if [[ -f "$KERNEL_PATH" ]]; then
    echo "[kernel] Using cached kernel: $KERNEL_PATH"
  else
    echo "[kernel] Downloading from $KERNEL_URL..."
    run curl -fL "$KERNEL_URL" -o "$KERNEL_PATH"
    echo "[kernel] Saved to $KERNEL_PATH"
  fi
fi

# ── Step 2: Build rootfs ──────────────────────────────────────────────────────
if [[ "$SKIP_ROOTFS" == "true" ]]; then
  echo "[rootfs] Skipping rootfs build (--skip-rootfs)"
  # Only require rootfs to exist when we actually need it (i.e. building a snapshot)
  if [[ "$SKIP_SNAPSHOT" != "true" && ! -f "$ROOTFS_PATH" ]]; then
    echo "ERROR: $ROOTFS_PATH not found (pass --skip-snapshot or build rootfs first)" >&2; exit 1
  fi
else
  echo "[rootfs] Building Python-${PYTHON_VERSION} rootfs..."
  # Detect if we're on Linux with loop device support
  ROOTFS_FLAGS="--name $SNAPSHOT_NAME --out $ROOTFS_PATH --size $ROOTFS_SIZE_MB --python $PYTHON_VERSION"
  if [[ "$DRY_RUN" == "true" ]] || [[ "$(uname -s)" != "Linux" ]]; then
    run "$SCRIPT_DIR/build-rootfs.sh" $ROOTFS_FLAGS --dry-run
  else
    run "$SCRIPT_DIR/build-rootfs.sh" $ROOTFS_FLAGS
  fi
  echo "[rootfs] Done: $ROOTFS_PATH"
fi

# ── Step 3: Build Firecracker snapshot ────────────────────────────────────────
if [[ "$SKIP_SNAPSHOT" == "true" ]]; then
  echo "[snapshot] Skipping snapshot build (--skip-snapshot)"
  if [[ ! -d "$SNAP_DIR" ]]; then
    echo "[snapshot] Creating placeholder snapshot dir for testing..."
    mkdir -p "$SNAP_DIR"
    echo '{"name":"'"$SNAPSHOT_NAME"'","version":"1.0.0","dry_run":true,"created_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' \
      > "$SNAP_DIR/meta.json"
    # Create placeholder binaries for MinIO upload testing
    [[ ! -f "$SNAP_DIR/state" ]] && dd if=/dev/zero of="$SNAP_DIR/state" bs=1K count=4 status=none
    [[ ! -f "$SNAP_DIR/mem"   ]] && dd if=/dev/zero of="$SNAP_DIR/mem"   bs=1M count=1 status=none
  fi
else
  [[ -z "$KERNEL_PATH" ]] && { echo "ERROR: --kernel or --download-kernel required for snapshot build" >&2; exit 1; }
  [[ ! -f "$ROOTFS_PATH" ]] && { echo "ERROR: rootfs not found: $ROOTFS_PATH" >&2; exit 1; }

  echo "[snapshot] Building Firecracker snapshot..."
  run "$SCRIPT_DIR/../../scripts/build-snapshot.sh" \
    --kernel "$KERNEL_PATH" \
    --rootfs "$ROOTFS_PATH" \
    --name   "$SNAPSHOT_NAME" \
    --out-dir "$OUT_DIR" \
    --vcpus  "$VCPUS" \
    --mem    "$MEM_MIB"
  echo "[snapshot] Done: $SNAP_DIR"
fi

# ── Step 4: Upload to MinIO ───────────────────────────────────────────────────
if [[ "$SKIP_UPLOAD" == "true" ]]; then
  echo "[upload] Skipping MinIO upload (--skip-upload)"
else
  echo "[upload] Uploading snapshot to MinIO..."
  UPLOAD_FLAGS="--snapshot-dir $SNAP_DIR --name $SNAPSHOT_NAME"
  [[ -n "$KERNEL_PATH" ]] && UPLOAD_FLAGS="$UPLOAD_FLAGS --kernel $KERNEL_PATH"
  [[ -f "$ROOTFS_PATH" ]] && UPLOAD_FLAGS="$UPLOAD_FLAGS --rootfs $ROOTFS_PATH"
  [[ "$DRY_RUN" == "true" ]] && UPLOAD_FLAGS="$UPLOAD_FLAGS --dry-run"
  run "$SCRIPT_DIR/upload-minio.sh" $UPLOAD_FLAGS
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Snapshot '${SNAPSHOT_NAME}' complete                "
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Local dir:  $SNAP_DIR"
echo "  meta.json:  $(cat "$SNAP_DIR/meta.json" 2>/dev/null | head -5 || echo '(see file)')"
echo ""
echo "To load this snapshot in the runtime:"
echo "  SNAPSHOT_NAME=$SNAPSHOT_NAME ./sandbox-platform/bin/fc-agent"
