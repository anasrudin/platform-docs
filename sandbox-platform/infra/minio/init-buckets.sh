#!/bin/bash
# init-buckets.sh
# Creates the required MinIO buckets for the platform.
#
# Requires: mc (MinIO Client) installed on PATH.
# Install:  wget https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc && chmod +x /usr/local/bin/mc
#
# Usage:
#   MINIO_ENDPOINT=http://localhost:9000 ./init-buckets.sh
#   # or use defaults (localhost)

set -euo pipefail

ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
ACCESS_KEY="${MINIO_ROOT_USER:-minioadmin}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:-minioadmin}"
ALIAS="platform-minio"

# ── Install mc if missing ─────────────────────────────────────────────────────
if ! command -v mc &>/dev/null; then
    echo "Installing MinIO client (mc)..."
    wget -q https://dl.min.io/client/mc/release/linux-amd64/mc \
        -O /usr/local/bin/mc
    chmod +x /usr/local/bin/mc
fi

# ── Configure alias ───────────────────────────────────────────────────────────
echo "Configuring mc alias '${ALIAS}' → ${ENDPOINT}"
mc alias set "${ALIAS}" "${ENDPOINT}" "${ACCESS_KEY}" "${SECRET_KEY}" --quiet

# ── Create buckets ────────────────────────────────────────────────────────────
BUCKETS=(
    "platform-artifacts"   # sandbox execution outputs (per-job)
    "platform-tools"       # compiled WASM modules + FC tool archives
    "platform-snapshots"   # Firecracker VM snapshots (kernel, rootfs, vmstate, memory)
)

for bucket in "${BUCKETS[@]}"; do
    if mc ls "${ALIAS}/${bucket}" &>/dev/null; then
        echo "  [skip] bucket already exists: ${bucket}"
    else
        mc mb "${ALIAS}/${bucket}"
        echo "  ✅ created bucket: ${bucket}"
    fi
done

# ── Bucket policies ───────────────────────────────────────────────────────────
# platform-artifacts: private (presigned URLs for download)
mc anonymous set none "${ALIAS}/platform-artifacts"

# platform-tools: private (agents pull via SDK, not public HTTP)
mc anonymous set none "${ALIAS}/platform-tools"

# platform-snapshots: private (sensitive VM images)
mc anonymous set none "${ALIAS}/platform-snapshots"

# ── Expected layout (reference) ───────────────────────────────────────────────
# platform-artifacts/
#   jobs/{job-id}/output.txt
#   jobs/{job-id}/record.json
#
# platform-tools/
#   wasm/{tool-name}/{version}.wasm
#   fc/{tool-name}/{version}/
#   gui/{tool-name}/{version}/
#
# platform-snapshots/
#   {snapshot-id}/kernel.bin
#   {snapshot-id}/rootfs.ext4
#   {snapshot-id}/vmstate.bin
#   {snapshot-id}/memory.bin

echo ""
echo "✅ MinIO buckets initialized."
mc ls "${ALIAS}"
