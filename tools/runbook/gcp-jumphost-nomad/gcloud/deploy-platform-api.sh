#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"

PROJECT_ID="${PROJECT_ID:-e2b-infra-489707}"
ZONE="${ZONE:-asia-southeast1-a}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
SSH_USER="${SSH_USER:-$USER}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"
API_PORT="${API_PORT:-8080}"
FC_POOL_SIZE="${FC_POOL_SIZE:-1}"
SKIP_SYNC="${SKIP_SYNC:-false}"

SRC_DIR="${ROOT_DIR}/sandbox-worker/src"
REMOTE_SRC_PARENT="/home/${SSH_USER}/platform-docs-runtime/sandbox-worker"
REMOTE_SRC_DIR="${REMOTE_SRC_PARENT}/src"
REMOTE_VENV="/home/${SSH_USER}/fc-agent-venv"
REMOTE_JOB="/tmp/platform-api.nomad"
GCLOUD_BIN="${GCLOUD_BIN:-/Users/annas/google-cloud-sdk/bin/gcloud}"
GCLOUD_CONFIG_DIR="${GCLOUD_CONFIG_DIR:-/tmp/gcloud-config}"

mkdir -p "${GCLOUD_CONFIG_DIR}"
if [[ -d "${HOME}/.config/gcloud" ]]; then
  cp -R "${HOME}/.config/gcloud/." "${GCLOUD_CONFIG_DIR}/" 2>/dev/null || true
fi
export CLOUDSDK_CONFIG="${GCLOUD_CONFIG_DIR}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require "${GCLOUD_BIN}"

if [[ "${SKIP_SYNC}" != "true" ]]; then
  "${GCLOUD_BIN}" compute ssh \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${NOMAD_NAME}" \
    --quiet \
    --command="mkdir -p '${REMOTE_SRC_PARENT}'"

  "${GCLOUD_BIN}" compute scp \
    --recurse \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${SRC_DIR}" \
    "${NOMAD_NAME}:${REMOTE_SRC_PARENT}/" \
    --quiet
fi

remote_script="$(mktemp)"
cat >"${remote_script}" <<EOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

PROJECT_ID="${PROJECT_ID}"
ZONE="${ZONE}"
NOMAD_NAME="${NOMAD_NAME}"
SSH_USER="${SSH_USER}"
SNAPSHOT_NAME="${SNAPSHOT_NAME}"
API_PORT="${API_PORT}"
FC_POOL_SIZE="${FC_POOL_SIZE}"
REMOTE_SRC_DIR="${REMOTE_SRC_DIR}"
REMOTE_VENV="${REMOTE_VENV}"
REMOTE_JOB="${REMOTE_JOB}"

test -x "\${REMOTE_VENV}/bin/python" || {
  echo "missing python venv: \${REMOTE_VENV}" >&2
  exit 1
}

NOMAD_ADDR=http://127.0.0.1:4646 nomad job stop -purge platform-api >/dev/null 2>&1 || true

# Kill orphan Firecracker processes — Nomad raw_exec does not kill child processes.
sudo pkill -x firecracker 2>/dev/null || true
sudo rm -f /tmp/vsock.sock 2>/dev/null || true
sleep 1

cat >"\${REMOTE_JOB}" <<JOB
job "platform-api" {
  datacenters = ["dc1"]
  type = "service"

  group "api" {
    count = 1

    network {
      port "http" {
        static = \${API_PORT}
      }
    }

    service {
      provider = "nomad"
      name = "platform-api"
      port = "http"
      tags = ["api", "gcp", "firecracker"]

      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "platform-api" {
      driver = "raw_exec"

      config {
        command = "\${REMOTE_VENV}/bin/python"
        args = ["-m", "api.app"]
      }

      env {
        API_PORT           = "\${API_PORT}"
        FC_MODE            = "real"
        FC_BINARY_PATH     = "/usr/bin/firecracker"
        FC_POOL_SIZE       = "\${FC_POOL_SIZE}"
        SNAPSHOT_NAME      = "\${SNAPSHOT_NAME}"
        FC_SNAPSHOT_BUCKET = "platform-snapshots"
        MINIO_ENDPOINT     = "http://127.0.0.1:9000"
        MINIO_ACCESS_KEY   = "minioadmin"
        MINIO_SECRET_KEY   = "minioadmin"
        PYTHONPATH         = "\${REMOTE_SRC_DIR}"
      }

      resources {
        cpu    = 1500
        memory = 2048
      }
    }
  }
}
JOB

NOMAD_ADDR=http://127.0.0.1:4646 nomad job run "\${REMOTE_JOB}"

for _ in \$(seq 1 60); do
  if curl -fsS "http://127.0.0.1:\${API_PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done

curl -fsS "http://127.0.0.1:\${API_PORT}/health"

SESSION=\$(
  curl -fsS -X POST "http://127.0.0.1:\${API_PORT}/sessions" \
    -H "Content-Type: application/json" \
    -d '{"runtime":"microvm"}' \
  | "\${REMOTE_VENV}/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["session_id"])'
)

echo "session: \${SESSION}"

curl -fsS -X POST "http://127.0.0.1:\${API_PORT}/execute" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"\${SESSION}\",\"tool\":\"python_run\",\"input\":{\"code\":\"print('hello from real VM')\"}}" \
  | "\${REMOTE_VENV}/bin/python" -m json.tool

NOMAD_ADDR=http://127.0.0.1:4646 nomad job status platform-api
EOF

"${GCLOUD_BIN}" compute ssh \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${NOMAD_NAME}" \
  --quiet \
  --command='bash -s' < "${remote_script}"

rm -f "${remote_script}"
