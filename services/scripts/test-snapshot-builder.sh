#!/usr/bin/env bash
# test-snapshot-builder.sh
# Tests the snapshot builder pipeline (build-rootfs, snapshot creation, upload dry-run).
# All tests use --dry-run and temp dirs — no Docker, Firecracker, or MinIO required.
#
# Usage:
#   bash scripts/test-snapshot-builder.sh [--keep]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB_DIR="${ROOT_DIR}/tools/snapshot-builder"

# Delegate to the snapshot-builder's own test suite.
exec bash "${SB_DIR}/test/test-snapshot-builder.sh" "$@"
