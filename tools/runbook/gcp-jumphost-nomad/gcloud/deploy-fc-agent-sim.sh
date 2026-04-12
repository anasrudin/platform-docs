#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-e2b-infra-489707}"
ZONE="${ZONE:-asia-southeast1-a}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"
API_HEALTH_PORT="${API_HEALTH_PORT:-8081}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
SRC_DIR="${ROOT_DIR}/sandbox-worker/src"
REMOTE_SRC_DIR="/tmp/src"
REMOTE_VENV="/tmp/sandbox-worker-venv"
REMOTE_CACHE_DIR="/tmp/sandbox-cache"
REMOTE_JOB="/tmp/sandbox-worker-sim.nomad"
GCLOUD_BIN="${GCLOUD_BIN:-/Users/annas/google-cloud-sdk/bin/gcloud}"
GCLOUD_CONFIG_DIR="${GCLOUD_CONFIG_DIR:-/tmp/gcloud-config}"

mkdir -p "${GCLOUD_CONFIG_DIR}"
if [[ -d "${HOME}/.config/gcloud" ]]; then
  cp -R "${HOME}/.config/gcloud/." "${GCLOUD_CONFIG_DIR}/" 2>/dev/null || true
fi
export CLOUDSDK_CONFIG="${GCLOUD_CONFIG_DIR}"

"${GCLOUD_BIN}" compute scp \
  --recurse \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${SRC_DIR}" \
  "${NOMAD_NAME}:/tmp/" \
  --quiet

remote_script="$(mktemp)"
cat >"${remote_script}" <<EOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

PROJECT_ID="${PROJECT_ID}"
ZONE="${ZONE}"
NOMAD_NAME="${NOMAD_NAME}"
SNAPSHOT_NAME="${SNAPSHOT_NAME}"
API_HEALTH_PORT="${API_HEALTH_PORT}"
REMOTE_SRC_DIR="${REMOTE_SRC_DIR}"
REMOTE_VENV="${REMOTE_VENV}"
REMOTE_CACHE_DIR="${REMOTE_CACHE_DIR}"
REMOTE_JOB="${REMOTE_JOB}"

sudo apt-get update
sudo apt-get install -y python3-venv

python3 -m venv "\${REMOTE_VENV}"
"\${REMOTE_VENV}/bin/pip" install --upgrade pip setuptools wheel
"\${REMOTE_VENV}/bin/pip" install fastapi uvicorn structlog

mkdir -p "\${REMOTE_CACHE_DIR}/\${SNAPSHOT_NAME}"
dd if=/dev/zero of="\${REMOTE_CACHE_DIR}/\${SNAPSHOT_NAME}/vmstate.bin" bs=1k count=4 status=none
dd if=/dev/zero of="\${REMOTE_CACHE_DIR}/\${SNAPSHOT_NAME}/memory.bin" bs=1k count=4 status=none
cat >"\${REMOTE_CACHE_DIR}/\${SNAPSHOT_NAME}/meta.json" <<META
{"name":"\${SNAPSHOT_NAME}","version":"3.12","kernel":"vmlinux-5.10","rootfs":"python-v1.ext4","vcpus":2,"mem_mib":512,"dry_run":true,"files":{}}
META

NOMAD_ADDR=http://127.0.0.1:4646 nomad job stop -purge nomad-demo-http >/dev/null 2>&1 || true

cat >"\${REMOTE_JOB}" <<JOB
job "sandbox-worker-sim" {
  datacenters = ["dc1"]
  type = "service"

  group "fc-agent" {
    count = 1

    network {
      port "api" {
        static = \${API_HEALTH_PORT}
      }
    }

    task "fc-agent" {
      driver = "raw_exec"

      config {
        command = "\${REMOTE_VENV}/bin/python"
        args = ["-c", "from agents.fc_agent import main; main()"]
      }

      env {
        FC_MODE            = "sim"
        API_HEALTH_PORT    = "\${API_HEALTH_PORT}"
        SNAPSHOT_NAME      = "\${SNAPSHOT_NAME}"
        SNAPSHOT_CACHE_DIR = "\${REMOTE_CACHE_DIR}"
        MINIO_ENDPOINT     = "http://127.0.0.1:9000"
        MINIO_ACCESS_KEY   = "minioadmin"
        MINIO_SECRET_KEY   = "minioadmin"
        MINIO_BUCKET       = "platform-snapshots"
        PYTHONPATH         = "\${REMOTE_SRC_DIR}"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
JOB

NOMAD_ADDR=http://127.0.0.1:4646 nomad job run "\${REMOTE_JOB}"

for _ in \$(seq 1 30); do
  if curl -fsS "http://127.0.0.1:\${API_HEALTH_PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done

curl -fsS "http://127.0.0.1:\${API_HEALTH_PORT}/health"
NOMAD_ADDR=http://127.0.0.1:4646 nomad job status sandbox-worker-sim
EOF

"${GCLOUD_BIN}" compute ssh \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${NOMAD_NAME}" \
  --quiet \
  --command='bash -s' < "${remote_script}"

rm -f "${remote_script}"
