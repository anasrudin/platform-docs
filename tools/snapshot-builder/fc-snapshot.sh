#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# fc-snapshot.sh — Firecracker VM snapshot builder
#
# Usage:
#   ./fc-snapshot.sh [OPTIONS]
#
# Options:
#   --kernel   PATH   Path to uncompressed vmlinux kernel (required)
#   --rootfs   PATH   Path to rootfs ext4 image (required)
#   --name     NAME   Snapshot name (default: default)
#   --out-dir  DIR    Output directory (default: /var/sandbox/snapshots)
#   --vcpus    N      vCPUs (default: 2)
#   --mem      MiB    Memory in MiB (default: 512)
#   --help            Print this help
#
# Output:
#   OUT_DIR/NAME/state   — Firecracker VM state file
#   OUT_DIR/NAME/mem     — Memory snapshot file
#   OUT_DIR/NAME/meta.json — Build metadata
#
# Requirements:
#   - firecracker binary at /usr/bin/firecracker
#   - jailer binary at /usr/bin/jailer (optional, for production)
#   - Root or CAP_NET_ADMIN for /dev/kvm access
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
KERNEL_PATH=""
ROOTFS_PATH=""
SNAPSHOT_NAME="default"
OUT_DIR="/var/sandbox/snapshots"
VCPUS=2
MEM_MIB=512
FC_BIN="/usr/bin/firecracker"
FC_SOCKET="/tmp/fc-builder-$$.sock"
FC_PID=""

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --kernel)   KERNEL_PATH="$2"; shift 2 ;;
    --rootfs)   ROOTFS_PATH="$2"; shift 2 ;;
    --name)     SNAPSHOT_NAME="$2"; shift 2 ;;
    --out-dir)  OUT_DIR="$2"; shift 2 ;;
    --vcpus)    VCPUS="$2"; shift 2 ;;
    --mem)      MEM_MIB="$2"; shift 2 ;;
    --help)     head -30 "$0" | grep '^#' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Validation ────────────────────────────────────────────────────────────────
[[ -z "$KERNEL_PATH" ]] && { echo "ERROR: --kernel is required" >&2; exit 1; }
[[ -z "$ROOTFS_PATH" ]] && { echo "ERROR: --rootfs is required" >&2; exit 1; }
[[ ! -f "$KERNEL_PATH" ]] && { echo "ERROR: kernel not found: $KERNEL_PATH" >&2; exit 1; }
[[ ! -f "$ROOTFS_PATH" ]] && { echo "ERROR: rootfs not found: $ROOTFS_PATH" >&2; exit 1; }
[[ ! -x "$FC_BIN" ]] && { echo "ERROR: firecracker not found at $FC_BIN" >&2; exit 1; }
command -v curl &>/dev/null || { echo "ERROR: curl not found" >&2; exit 1; }

SNAP_DIR="$OUT_DIR/$SNAPSHOT_NAME"

echo "=== Firecracker Snapshot Builder ==="
echo "  Kernel:   $KERNEL_PATH"
echo "  Rootfs:   $ROOTFS_PATH"
echo "  Name:     $SNAPSHOT_NAME"
echo "  Output:   $SNAP_DIR"
echo "  vCPUs:    $VCPUS"
echo "  Memory:   ${MEM_MIB}MiB"
echo ""

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  if [[ -n "$FC_PID" ]] && kill -0 "$FC_PID" 2>/dev/null; then
    echo "Stopping Firecracker (PID=$FC_PID)..."
    kill "$FC_PID" 2>/dev/null || true
    wait "$FC_PID" 2>/dev/null || true
  fi
  rm -f "$FC_SOCKET"
}
trap cleanup EXIT

# ── Helper: call Firecracker API ──────────────────────────────────────────────
fc_api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local response status response_body
  local curl_args=(
    -sS
    --unix-socket "$FC_SOCKET"
    -X "$method"
    -H "Content-Type: application/json"
    -w $'\n%{http_code}'
  )

  [[ -n "$body" ]] && curl_args+=(-d "$body")

  response="$(curl "${curl_args[@]}" "http://localhost$path")" || {
    echo "ERROR: Firecracker API request failed: $method $path" >&2
    return 1
  }

  status="${response##*$'\n'}"
  response_body="${response%$'\n'*}"

  if [[ ! "$status" =~ ^2[0-9]{2}$ ]]; then
    if [[ -n "$response_body" ]]; then
      echo "ERROR: Firecracker API $method $path returned HTTP $status: $response_body" >&2
    else
      echo "ERROR: Firecracker API $method $path returned HTTP $status" >&2
    fi
    return 1
  fi

  printf '%s' "$response_body"
}

# ── Step 1: Create output directory ──────────────────────────────────────────
echo "[1/6] Creating snapshot directory..."
mkdir -p "$SNAP_DIR"

# ── Step 2: Start Firecracker ─────────────────────────────────────────────────
echo "[2/6] Starting Firecracker..."
"$FC_BIN" --api-sock "$FC_SOCKET" --log-level Error &
FC_PID=$!

# Wait for socket to appear (up to 3s).
for i in $(seq 1 30); do
  [[ -S "$FC_SOCKET" ]] && break
  if ! kill -0 "$FC_PID" 2>/dev/null; then
    wait "$FC_PID" 2>/dev/null || true
    echo "ERROR: Firecracker exited before API socket was ready" >&2
    exit 1
  fi
  sleep 0.1
done
[[ -S "$FC_SOCKET" ]] || { echo "ERROR: Firecracker socket not ready" >&2; exit 1; }
echo "  Firecracker started (PID=$FC_PID)"

# ── Step 3: Configure VM ─────────────────────────────────────────────────────
echo "[3/6] Configuring VM..."

# Boot source
fc_api PUT /boot-source "{
  \"kernel_image_path\": \"$KERNEL_PATH\",
  \"boot_args\": \"console=ttyS0 reboot=k panic=1 pci=off\"
}" > /dev/null

# Root drive
fc_api PUT /drives/rootfs "{
  \"drive_id\": \"rootfs\",
  \"path_on_host\": \"$ROOTFS_PATH\",
  \"is_root_device\": true,
  \"is_read_only\": false
}" > /dev/null

# Machine config
fc_api PUT /machine-config "{
  \"vcpu_count\": $VCPUS,
  \"mem_size_mib\": $MEM_MIB,
  \"smt\": false
}" > /dev/null

echo "  VM configured"

# ── Step 4: Boot the VM ────────────────────────────────────────────────────────
echo "[4/6] Booting VM (this may take 10-30 seconds)..."
fc_api PUT /actions '{"action_type": "InstanceStart"}' > /dev/null

# Wait for the guest to become ready (poll for a ready file or fixed delay).
# In production: replace with a gRPC health check to the guest agent.
BOOT_TIMEOUT=30
for i in $(seq 1 $BOOT_TIMEOUT); do
  if ! kill -0 "$FC_PID" 2>/dev/null; then
    wait "$FC_PID" 2>/dev/null || true
    echo "" >&2
    echo "ERROR: Firecracker exited before snapshot capture completed" >&2
    exit 1
  fi
  sleep 1
  echo -n "."
done
echo ""
echo "  VM booted"

# ── Step 5: Pause VM and take snapshot ────────────────────────────────────────
echo "[5/6] Pausing VM and creating snapshot..."

fc_api PATCH /vm '{"state": "Paused"}' > /dev/null
echo "  VM paused"

SNAP_RESPONSE=$(fc_api PUT /snapshot/create "{
  \"snapshot_type\": \"Full\",
  \"snapshot_path\": \"$SNAP_DIR/state\",
  \"mem_file_path\": \"$SNAP_DIR/mem\",
  \"version\": \"1.0.0\"
}")
echo "  Snapshot response: $SNAP_RESPONSE"

[[ -s "$SNAP_DIR/state" ]] || { echo "ERROR: snapshot state file missing or empty: $SNAP_DIR/state" >&2; exit 1; }
[[ -s "$SNAP_DIR/mem"   ]] || { echo "ERROR: snapshot memory file missing or empty: $SNAP_DIR/mem" >&2; exit 1; }

# ── Step 6: Write metadata ────────────────────────────────────────────────────
echo "[6/6] Writing metadata..."
cat > "$SNAP_DIR/meta.json" << METAEOF
{
  "name": "$SNAPSHOT_NAME",
  "kernel": "$KERNEL_PATH",
  "rootfs": "$ROOTFS_PATH",
  "vcpus": $VCPUS,
  "mem_mib": $MEM_MIB,
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "files": {
    "state": "$SNAP_DIR/state",
    "mem":   "$SNAP_DIR/mem"
  }
}
METAEOF

echo ""
echo "=== Snapshot built successfully ==="
echo "  State: $SNAP_DIR/state"
echo "  Mem:   $SNAP_DIR/mem"
echo "  Meta:  $SNAP_DIR/meta.json"
echo ""
echo "To load this snapshot:"
echo "  SNAPSHOT_NAME=$SNAPSHOT_NAME fc-agent"
