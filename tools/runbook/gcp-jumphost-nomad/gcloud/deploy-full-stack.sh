#!/usr/bin/env bash
# deploy-full-stack.sh — Deploy complete platform stack to GCP Nomad VM
#
# Layer layout (all on one server for now):
#   controller  → Nomad, Consul, platform-api
#   worker      → Firecracker pool (real or sim)
#   data        → MinIO, PostgreSQL, Redis, Jaeger
#
# Layer host config is read from config/topology.env.
# Generate it with: ./gcloud/gen-topology.sh
#
# Usage:
#   ./deploy-full-stack.sh [OPTIONS]
#
# Options:
#   --skip-sync      Skip rsync of services/ and sandbox-worker/
#   --skip-firewall  Skip gcloud firewall rule
#   --skip-nomad     Skip platform-api Nomad redeploy
#   --fc-mode MODE   FC_MODE for the Nomad job: sim (default) or real
#   --my-ip IP       Your public IP (default: auto-detect)
#   --internal-ip    Use VM internal IP for gcloud ssh/scp (use when running
#                    from inside the VPC, e.g. from the jumphost)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNBOOK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# PLATFORM_ROOT can be overridden when running on a jumphost where the repo
# layout differs from the local checkout.
ROOT_DIR="${PLATFORM_ROOT:-$(cd "${RUNBOOK_DIR}/../../../.." && pwd)}"

# ── Load topology config ──────────────────────────────────────────────────────
TOPOLOGY_FILE="${RUNBOOK_DIR}/config/topology.env"

if [[ -f "${TOPOLOGY_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${TOPOLOGY_FILE}"
  echo "Loaded topology: ${TOPOLOGY_FILE}"
else
  echo "WARN: config/topology.env not found." >&2
  echo "  Run:  ./gcloud/gen-topology.sh" >&2
  echo "  Or:   cp config/topology.env.example config/topology.env  and fill in the IP." >&2
  echo ""
fi

# ── Config (fall back to env vars if topology is absent) ─────────────────────
PROJECT_ID="${PROJECT_ID:-e2b-infra-489707}"
ZONE="${ZONE:-asia-southeast1-a}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
SSH_USER="${SSH_USER:-$USER}"
GCLOUD_BIN="${GCLOUD_BIN:-gcloud}"

# Layer hosts — all default to CONTROLLER_HOST if not set separately
CONTROLLER_HOST="${CONTROLLER_HOST:-}"
WORKER_HOST="${WORKER_HOST:-${CONTROLLER_HOST}}"
DATA_HOST="${DATA_HOST:-${CONTROLLER_HOST}}"

SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"
API_PORT="${API_PORT:-8080}"
FC_POOL_SIZE="${FC_POOL_SIZE:-1}"
FC_MODE="${FC_MODE:-sim}"   # default sim — safe without a real snapshot

SKIP_SYNC=false
SKIP_FIREWALL=false
SKIP_NOMAD=false
MY_IP=""
# Use --internal-ip when running from inside the VPC (e.g. jumphost).
# Routes gcloud ssh/scp via private IP so VPC source_tags firewall rules match.
USE_INTERNAL_IP="${USE_INTERNAL_IP:-false}"

for arg in "$@"; do
  case "$arg" in
    --skip-sync)      SKIP_SYNC=true ;;
    --skip-firewall)  SKIP_FIREWALL=true ;;
    --skip-nomad)     SKIP_NOMAD=true ;;
    --fc-mode)        shift; FC_MODE="${1:-sim}" ;;
    --fc-mode=*)      FC_MODE="${arg#--fc-mode=}" ;;
    --my-ip)          shift; MY_IP="${1:-}" ;;
    --my-ip=*)        MY_IP="${arg#--my-ip=}" ;;
    --internal-ip)    USE_INTERNAL_IP=true ;;
  esac
done

# Build the --internal-ip flag string (empty when not needed)
_IIPFLAG=""
[[ "${USE_INTERNAL_IP}" == "true" ]] && _IIPFLAG="--internal-ip"

# Auto-detect public IP
if [[ -z "$MY_IP" ]]; then
  MY_IP="$(curl -fsS https://checkip.amazonaws.com || curl -fsS https://icanhazip.com)"
  MY_IP="${MY_IP%/32}"
fi
MY_CIDR="${MY_IP}/32"

SRC_SERVICES="${ROOT_DIR}/services"
SRC_WORKER="${ROOT_DIR}/sandbox-worker"
REMOTE_SERVICES="/home/${SSH_USER}/platform-docs/services"
REMOTE_WORKER="/home/${SSH_USER}/platform-docs/sandbox-worker"
REMOTE_VENV="/home/${SSH_USER}/fc-agent-venv"
REMOTE_SRC_DIR="${REMOTE_WORKER}/src"
REMOTE_JOB="/tmp/platform-api.nomad"

# ── Helper: print dashboard URLs ─────────────────────────────────────────────
print_urls() {
  local C="${CONTROLLER_HOST:-<controller-ip>}"
  local D="${DATA_HOST:-${C}}"
  echo ""
  echo "  Dashboards:"
  echo "    [controller] Nomad:   http://${C}:4646"
  echo "    [controller] Consul:  http://${C}:8500"
  echo "    [controller] API:     http://${C}:${API_PORT}/health"
  echo "    [data]       Jaeger:  http://${D}:16686"
  echo "    [data]       MinIO:   http://${D}:9001  (minioadmin / minioadmin)"
  echo ""
  echo "  Smoke test:"
  echo "    ${RUNBOOK_DIR}/smoke-test.sh http://${C}:${API_PORT}"
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo "=== Deploy full platform stack → GCP Nomad ==="
echo "  Project:    ${PROJECT_ID} / ${ZONE} / ${NOMAD_NAME}"
echo "  FC_MODE:    ${FC_MODE}"
echo "  My IP:      ${MY_CIDR}"
echo ""
echo "  Layer topology:"
echo "    controller: ${CONTROLLER_HOST:-<not set>}  (Nomad, Consul, platform-api)"
echo "    worker:     ${WORKER_HOST:-<not set>}  (Firecracker)"
echo "    data:       ${DATA_HOST:-<not set>}  (PG, Redis, MinIO, Jaeger)"
echo ""
echo "  Skip sync: ${SKIP_SYNC} | skip firewall: ${SKIP_FIREWALL} | skip nomad: ${SKIP_NOMAD}"
echo "  Internal IP: ${USE_INTERNAL_IP}"
echo ""

# ── Step 0: Wait for VM bootstrap (Nomad + Docker) ───────────────────────────
echo "[0/5] Waiting for VM bootstrap (Nomad + Docker to be ready)..."
echo "  This takes ~2 min on a fresh VM."

# shellcheck disable=SC2086
"${GCLOUD_BIN}" compute ssh \
  ${_IIPFLAG} \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${NOMAD_NAME}" \
  --quiet \
  --command='
set -euo pipefail
MAX=120
INTERVAL=5
elapsed=0

while [[ ! -f /var/lib/nomad-bootstrap-complete ]]; do
  if (( elapsed >= MAX )); then
    echo "ERROR: VM bootstrap did not complete after ${MAX}s." >&2
    exit 1
  fi
  echo "  waiting for bootstrap... (${elapsed}s)"
  sleep "${INTERVAL}"
  (( elapsed += INTERVAL )) || true
done
echo "  bootstrap marker found."

until NOMAD_ADDR=http://127.0.0.1:4646 nomad status >/dev/null 2>&1; do
  if (( elapsed >= MAX )); then
    echo "ERROR: Nomad did not become ready after ${MAX}s." >&2
    exit 1
  fi
  echo "  waiting for Nomad... (${elapsed}s)"
  sleep "${INTERVAL}"
  (( elapsed += INTERVAL )) || true
done
echo "  Nomad is ready."

until docker info >/dev/null 2>&1; do
  if (( elapsed >= MAX )); then
    echo "ERROR: Docker did not become ready after ${MAX}s." >&2
    exit 1
  fi
  echo "  waiting for Docker... (${elapsed}s)"
  sleep "${INTERVAL}"
  (( elapsed += INTERVAL )) || true
done
echo "  Docker is ready."
'

echo "  VM is ready."
echo ""

# ── Step 1: Sync services/ and sandbox-worker/ ───────────────────────────────
if [[ "${SKIP_SYNC}" == "false" ]]; then
  echo "[1/5] Syncing services/ and sandbox-worker/ to VM..."

  # shellcheck disable=SC2086
  "${GCLOUD_BIN}" compute ssh \
    ${_IIPFLAG} \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${NOMAD_NAME}" \
    --quiet \
    --command="mkdir -p '${REMOTE_SERVICES}' '${REMOTE_WORKER}'"

  # shellcheck disable=SC2086
  "${GCLOUD_BIN}" compute scp \
    ${_IIPFLAG} \
    --recurse \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${SRC_SERVICES}/." \
    "${NOMAD_NAME}:${REMOTE_SERVICES}/" \
    --quiet

  # shellcheck disable=SC2086
  "${GCLOUD_BIN}" compute scp \
    ${_IIPFLAG} \
    --recurse \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${SRC_WORKER}/." \
    "${NOMAD_NAME}:${REMOTE_WORKER}/" \
    --quiet

  echo "  done."
else
  echo "[1/5] Skipping sync (--skip-sync)"
fi

echo ""

# ── Step 2: Install Python venv + app ────────────────────────────────────────
echo "[2/5] Installing Python venv and app dependencies on VM..."

# Use a temp script to avoid quoting issues with the heredoc
_venv_script="$(mktemp)"
cat >"${_venv_script}" <<VENVEOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

REMOTE_VENV="${REMOTE_VENV}"
REMOTE_WORKER="${REMOTE_WORKER}"

# Ensure python3-venv is available
if ! python3 -m venv --help >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y python3-venv python3-pip -qq
fi

if [[ ! -x "\${REMOTE_VENV}/bin/python" ]]; then
  echo "  Creating venv at \${REMOTE_VENV}..."
  python3 -m venv "\${REMOTE_VENV}"
  "\${REMOTE_VENV}/bin/pip" install --upgrade pip setuptools wheel -q
fi

echo "  Installing sandbox-worker app..."
cd "\${REMOTE_WORKER}"
"\${REMOTE_VENV}/bin/pip" install -e ".[dev]" -q

echo "  Venv ready: \$("\${REMOTE_VENV}/bin/python" --version)"
VENVEOF

# shellcheck disable=SC2086
"${GCLOUD_BIN}" compute ssh \
  ${_IIPFLAG} \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${NOMAD_NAME}" \
  --quiet \
  --command='bash -s' < "${_venv_script}"

rm -f "${_venv_script}"
echo ""

# ── Step 3: Start data layer containers ──────────────────────────────────────
echo "[3/5] Starting data layer containers (MinIO, PG, Redis, Consul, Jaeger)..."

# shellcheck disable=SC2086
"${GCLOUD_BIN}" compute ssh \
  ${_IIPFLAG} \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${NOMAD_NAME}" \
  --quiet \
  --command='
set -euo pipefail

SERVICES_DIR="${HOME}/platform-docs/services"

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose (v2) not found." >&2
  exit 1
fi

echo "  Creating external volumes (idempotent)..."
docker volume create --name data_minio_data 2>/dev/null || true

echo "  Bringing up data layer services..."
cd "${SERVICES_DIR}"
docker compose up -d --remove-orphans

echo ""
echo "  Waiting for containers to be healthy..."
for i in $(seq 1 30); do
  unhealthy=$(docker compose ps --format json 2>/dev/null \
    | python3 -c "
import json, sys
rows = []
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try: rows.append(json.loads(line))
    except: pass
bad = [r.get(\"Name\",\"?\") for r in rows if r.get(\"Health\",\"\") not in (\"healthy\",\"\")]
print(\" \".join(bad))
" 2>/dev/null || echo "")
  if [[ -z "$unhealthy" ]]; then
    echo "  All containers healthy."
    break
  fi
  echo "  Waiting... (unhealthy: $unhealthy)"
  sleep 3
done

echo ""
docker compose ps
'

echo ""

# ── Step 4: Open firewall ports ───────────────────────────────────────────────
if [[ "${SKIP_FIREWALL}" == "false" ]]; then
  echo "[4/5] Opening firewall ports for ${MY_CIDR}..."

  RULE_NAME="platform-dev-access"
  ALL_PORTS="tcp:4646,tcp:8500,tcp:8080,tcp:9001,tcp:16686,tcp:4317,tcp:4318"

  if "${GCLOUD_BIN}" compute firewall-rules describe "${RULE_NAME}" \
      --project="${PROJECT_ID}" \
      --format="value(name)" >/dev/null 2>&1; then
    echo "  Updating rule: ${RULE_NAME}"
    "${GCLOUD_BIN}" compute firewall-rules update "${RULE_NAME}" \
      --project="${PROJECT_ID}" \
      --source-ranges="${MY_CIDR}" \
      --allow="${ALL_PORTS}" \
      --quiet
  else
    echo "  Creating rule: ${RULE_NAME}"
    "${GCLOUD_BIN}" compute firewall-rules create "${RULE_NAME}" \
      --project="${PROJECT_ID}" \
      --direction=INGRESS \
      --priority=1000 \
      --network=default \
      --action=ALLOW \
      --rules="${ALL_PORTS}" \
      --source-ranges="${MY_CIDR}" \
      --target-tags=nomad \
      --description="Platform dev UI access — controller/worker/data layer ports" \
      --quiet
  fi

  echo "  Firewall rule applied."
  print_urls
else
  echo "[4/5] Skipping firewall update (--skip-firewall)"
fi

echo ""

# ── Step 5: Deploy controller layer (platform-api Nomad job) ─────────────────
if [[ "${SKIP_NOMAD}" == "false" ]]; then
  echo "[5/5] Deploying controller layer: platform-api Nomad job (FC_MODE=${FC_MODE})..."

  remote_script="$(mktemp)"
  cat >"${remote_script}" <<EOF
set -euo pipefail

SSH_USER="${SSH_USER}"
SNAPSHOT_NAME="${SNAPSHOT_NAME}"
API_PORT="${API_PORT}"
FC_POOL_SIZE="${FC_POOL_SIZE}"
FC_MODE="${FC_MODE}"
REMOTE_SRC_DIR="${REMOTE_SRC_DIR}"
REMOTE_VENV="${REMOTE_VENV}"
REMOTE_JOB="${REMOTE_JOB}"

DATA_HOST="127.0.0.1"

# Guard: venv must exist (created in step 2)
test -x "\${REMOTE_VENV}/bin/python" || {
  echo "ERROR: venv not found at \${REMOTE_VENV} — step 2 may have failed." >&2
  exit 1
}

NOMAD_ADDR=http://127.0.0.1:4646 nomad job stop -purge platform-api >/dev/null 2>&1 || true
sudo pkill -x firecracker 2>/dev/null || true
sudo rm -f /tmp/vsock.sock 2>/dev/null || true
sleep 1

cat >"\${REMOTE_JOB}" <<JOB
job "platform-api" {
  datacenters = ["dc1"]
  type = "service"

  group "controller" {
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
      tags = ["api", "gcp", "controller-layer"]

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
        API_PORT   = "\${API_PORT}"
        PYTHONPATH = "\${REMOTE_SRC_DIR}"

        # worker layer
        FC_MODE            = "\${FC_MODE}"
        FC_BINARY_PATH     = "/usr/bin/firecracker"
        FC_POOL_SIZE       = "\${FC_POOL_SIZE}"
        SNAPSHOT_NAME      = "\${SNAPSHOT_NAME}"

        # data layer — storage
        FC_SNAPSHOT_BUCKET = "platform-snapshots"
        MINIO_ENDPOINT     = "http://\${DATA_HOST}:9000"
        MINIO_ACCESS_KEY   = "minioadmin"
        MINIO_SECRET_KEY   = "minioadmin"
        DATABASE_URL       = "postgresql://postgres:postgres@\${DATA_HOST}:5432/platform"
        REDIS_URL          = "redis://\${DATA_HOST}:6379/0"

        # data layer — observability
        OTEL_ENABLED                = "true"
        OTEL_EXPORTER_OTLP_ENDPOINT = "http://\${DATA_HOST}:4317"

        # controller layer — service registry
        CONSUL_ENABLED = "true"
        CONSUL_HOST    = "127.0.0.1"
        CONSUL_PORT    = "8500"
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

echo "Waiting for /health..."
for _ in \$(seq 1 60); do
  if curl -fsS "http://127.0.0.1:\${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "http://127.0.0.1:\${API_PORT}/health" | python3 -m json.tool
NOMAD_ADDR=http://127.0.0.1:4646 nomad job status platform-api
EOF

  # shellcheck disable=SC2086
  "${GCLOUD_BIN}" compute ssh \
    ${_IIPFLAG} \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${NOMAD_NAME}" \
    --quiet \
    --command='bash -s' < "${remote_script}"

  rm -f "${remote_script}"

  echo ""
  echo "  platform-api (controller layer) deployed with FC_MODE=${FC_MODE}."
else
  echo "[5/5] Skipping Nomad redeploy (--skip-nomad)"
fi

echo ""
echo "=== Done. Full stack is up. ==="
print_urls
