#!/usr/bin/env bash
# cleanup.sh — tear down the GCP Nomad platform-api deployment
#
# Stops the Nomad job, kills orphan Firecracker processes, and optionally
# removes the snapshot from MinIO and the local cache.
#
# Usage:
#   ./cleanup.sh [--full]
#
#   --full   Also delete the snapshot from MinIO and clear the local snapshot cache.
#            Without this flag, only the running job and FC processes are stopped.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ID="${PROJECT_ID:-e2b-infra-489707}"
ZONE="${ZONE:-asia-southeast1-a}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"
GCLOUD_BIN="${GCLOUD_BIN:-/Users/annas/google-cloud-sdk/bin/gcloud}"
FULL=false

for arg in "$@"; do
  [[ "$arg" == "--full" ]] && FULL=true
done

echo "=== Cleanup: GCP Nomad platform-api ==="
echo "  Project: $PROJECT_ID / $ZONE / $NOMAD_NAME"
echo "  Full:    $FULL"
echo ""

"$GCLOUD_BIN" compute ssh \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  "$NOMAD_NAME" \
  --quiet \
  --command="$(cat <<REMOTE
set -euo pipefail
SNAPSHOT_NAME="$SNAPSHOT_NAME"
FULL="$FULL"

echo "[1/3] Stopping Nomad job..."
NOMAD_ADDR=http://127.0.0.1:4646 nomad job stop -purge platform-api 2>/dev/null && echo "  stopped" || echo "  (not running)"

echo "[2/3] Killing orphan Firecracker processes..."
sudo pkill -x firecracker 2>/dev/null && echo "  killed" || echo "  (none running)"
sudo rm -f /tmp/vsock.sock 2>/dev/null || true

if [[ "\$FULL" == "true" ]]; then
  echo "[3/3] Removing snapshot from MinIO and local cache..."
  mc alias set local http://127.0.0.1:9000 minioadmin minioadmin --quiet 2>/dev/null || true
  mc rm --recursive --force "local/platform-snapshots/\$SNAPSHOT_NAME" 2>/dev/null && echo "  MinIO snapshot removed" || echo "  (not in MinIO)"
  sudo rm -rf "/tmp/platform-snapshots/\$SNAPSHOT_NAME" 2>/dev/null && echo "  Local cache cleared" || true
else
  echo "[3/3] Skipping snapshot removal (use --full to also delete from MinIO and cache)"
fi

echo ""
echo "Done."
REMOTE
)"
