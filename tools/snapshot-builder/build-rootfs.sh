#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build-rootfs.sh — Build a Python-optimized ext4 rootfs image for Firecracker
#
# Usage:
#   ./build-rootfs.sh [OPTIONS]
#
# Options:
#   --name     NAME   Snapshot name  (default: python-v1)
#   --out      PATH   Output .ext4 path (default: /var/sandbox/cache/<name>.ext4)
#   --size     MiB    Rootfs size in MiB (default: 1024)
#   --python   VER    Python version tag (default: 3.11)
#   --dry-run         Create a placeholder file instead of a real image
#
# Requirements:
#   - Docker daemon running (for rootfs export)
#   - mkfs.ext4, dd (util-linux)
#   - Root or sudo for loop-mount (Linux only)
#
# Output:
#   <out>.ext4  — ext4 rootfs image ready for Firecracker
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SNAPSHOT_NAME="python-v1"
OUT_PATH=""
ROOTFS_SIZE_MB=1024
PYTHON_VERSION="3.11"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)       SNAPSHOT_NAME="$2"; shift 2 ;;
    --out)        OUT_PATH="$2"; shift 2 ;;
    --size)       ROOTFS_SIZE_MB="$2"; shift 2 ;;
    --python)     PYTHON_VERSION="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --help)       grep '^#' "$0" | head -20 | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

CACHE_DIR="${SNAPSHOT_CACHE_DIR:-/var/sandbox/cache}"
OUT_PATH="${OUT_PATH:-$CACHE_DIR/${SNAPSHOT_NAME}.ext4}"
mkdir -p "$(dirname "$OUT_PATH")"

echo "=== Rootfs Builder ==="
echo "  Name:    $SNAPSHOT_NAME"
echo "  Python:  $PYTHON_VERSION"
echo "  Size:    ${ROOTFS_SIZE_MB}MiB"
echo "  Output:  $OUT_PATH"
echo ""

# ── Dry-run mode (no Docker/KVM required) ─────────────────────────────────
if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] Creating placeholder rootfs (${ROOTFS_SIZE_MB}MiB)..."
  dd if=/dev/zero of="$OUT_PATH" bs=1M count="$ROOTFS_SIZE_MB" status=none
  # Attempt to format if mkfs.ext4 is available
  if command -v mkfs.ext4 &>/dev/null; then
    mkfs.ext4 -q -L "python-rootfs" "$OUT_PATH"
    echo "[dry-run] Formatted as ext4 (empty, no Python packages)"
  else
    echo "[dry-run] mkfs.ext4 not available — raw zero-filled image created"
  fi
  echo "  => $OUT_PATH"
  exit 0
fi

# ── Validate prerequisites ────────────────────────────────────────────────
for cmd in docker dd mkfs.ext4; do
  command -v "$cmd" &>/dev/null || { echo "ERROR: $cmd not found" >&2; exit 1; }
done

# Linux-only: loop device for mounting
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: Full rootfs build requires Linux (loop mount). Use --dry-run on macOS." >&2
  exit 1
fi

DOCKER_IMAGE="python:${PYTHON_VERSION}-slim-bookworm"
WORK_DIR="$(mktemp -d /tmp/rootfs-build-XXXXXX)"
ROOTFS_DIR="$WORK_DIR/rootfs"

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

echo "[1/5] Pulling base image: $DOCKER_IMAGE..."
docker pull --quiet "$DOCKER_IMAGE"

echo "[2/5] Exporting rootfs from Docker..."
mkdir -p "$ROOTFS_DIR"
docker create --name "rootfs-export-$$" "$DOCKER_IMAGE" /bin/true
docker export "rootfs-export-$$" | tar -x -C "$ROOTFS_DIR"
docker rm "rootfs-export-$$"

echo "[3/5] Installing guest agent and Python packages..."
# Write the guest agent into the rootfs
mkdir -p "$ROOTFS_DIR/opt/agent"
cat > "$ROOTFS_DIR/opt/agent/agent.py" << 'AGENTEOF'
#!/usr/bin/env python3
"""
Sandbox guest agent — receives jobs via vsock and executes them.
Listens on vsock port 8080 (TCP fallback: 0.0.0.0:8080 for dev).
"""
import json
import os
import socket
import subprocess
import sys
import traceback

AF_VSOCK = 40
VMADDR_CID_ANY = 0xFFFFFFFF
VSOCK_PORT = 8080

def handle_request(conn):
    buf = b""
    while b"\n\n" not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            return
        buf += chunk
    try:
        payload = json.loads(buf.split(b"\n\n", 1)[1])
    except Exception:
        conn.sendall(json.dumps({"exit_code": 1, "stdout": "", "stderr": "bad payload"}).encode() + b"\n")
        return

    tool  = payload.get("tool", "")
    input_data = payload.get("input", {})
    try:
        result = dispatch(tool, input_data)
        response = {"exit_code": 0, "stdout": json.dumps(result), "stderr": ""}
    except Exception as exc:
        response = {"exit_code": 1, "stdout": "", "stderr": traceback.format_exc()}

    conn.sendall(json.dumps(response).encode() + b"\n")

def dispatch(tool, input_data):
    if tool == "python_run":
        code = input_data.get("code", "")
        proc = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=30
        )
        return {"stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    elif tool == "bash_run":
        cmd = input_data.get("command", "echo hello")
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        return {"stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    elif tool == "echo":
        return {"output": input_data.get("message", "")}
    else:
        raise ValueError(f"unknown tool: {tool}")

def main():
    # Try vsock first (production), fall back to TCP (dev/test)
    use_vsock = hasattr(socket, "AF_VSOCK") or AF_VSOCK == 40
    if use_vsock:
        try:
            srv = socket.socket(AF_VSOCK, socket.SOCK_STREAM)
            srv.bind((VMADDR_CID_ANY, VSOCK_PORT))
            srv.listen(10)
            print(f"[agent] listening on vsock:{VSOCK_PORT}", flush=True)
        except OSError:
            use_vsock = False

    if not use_vsock:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", VSOCK_PORT))
        srv.listen(10)
        print(f"[agent] listening on tcp:0.0.0.0:{VSOCK_PORT}", flush=True)

    while True:
        conn, _ = srv.accept()
        try:
            handle_request(conn)
        finally:
            conn.close()

if __name__ == "__main__":
    main()
AGENTEOF

chmod +x "$ROOTFS_DIR/opt/agent/agent.py"

# Init script that runs agent on boot
mkdir -p "$ROOTFS_DIR/etc/init.d"
cat > "$ROOTFS_DIR/etc/init.d/agent" << 'INITEOF'
#!/bin/sh
case "$1" in
  start) /opt/agent/agent.py &;;
  stop)  pkill -f agent.py;;
esac
INITEOF
chmod +x "$ROOTFS_DIR/etc/init.d/agent"

# inittab: run agent on boot
cat > "$ROOTFS_DIR/etc/inittab" << 'INITTABEOF'
::sysinit:/etc/init.d/rcS
::respawn:/opt/agent/agent.py
INITTABEOF

echo "[4/5] Creating ext4 image (${ROOTFS_SIZE_MB}MiB)..."
dd if=/dev/zero of="$OUT_PATH" bs=1M count="$ROOTFS_SIZE_MB" status=none
mkfs.ext4 -q -L "python-rootfs" "$OUT_PATH"

MOUNT_DIR="$WORK_DIR/mnt"
mkdir -p "$MOUNT_DIR"
mount -o loop "$OUT_PATH" "$MOUNT_DIR"
trap "umount $MOUNT_DIR; rm -rf $WORK_DIR" EXIT

cp -a "$ROOTFS_DIR/." "$MOUNT_DIR/"

echo "[5/5] Unmounting and finalising..."
umount "$MOUNT_DIR"
trap cleanup EXIT

echo ""
echo "=== Rootfs built ==="
echo "  Image:  $OUT_PATH"
echo "  Size:   $(du -sh "$OUT_PATH" | cut -f1)"
