#!/usr/bin/env bash
# deploy-full-stack.sh — deploy the complete platform stack on the GCP Nomad VM
#
# Syncs the services/ docker-compose tree to the VM, starts all containers
# (MinIO, PostgreSQL, Redis, Consul, Jaeger), opens firewall rules for UI
# access, then redeploys the platform-api Nomad job with full env wiring.
#
# Usage:
#   ./deploy-full-stack.sh [OPTIONS]
#
# Options:
#   --skip-sync      Skip rsync of services/ (use when nothing changed)
#   --skip-firewall  Skip gcloud firewall rule creation
#   --skip-nomad     Skip platform-api Nomad redeploy
#   --my-ip IP       Your public IP for firewall rules (default: auto-detect)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:-e2b-infra-489707}"
ZONE="${ZONE:-asia-southeast1-a}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
SSH_USER="${SSH_USER:-$USER}"
GCLOUD_BIN="${GCLOUD_BIN:-/Users/annas/google-cloud-sdk/bin/gcloud}"

SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"
API_PORT="${API_PORT:-8080}"
FC_POOL_SIZE="${FC_POOL_SIZE:-1}"

SKIP_SYNC=false
SKIP_FIREWALL=false
SKIP_NOMAD=false
MY_IP=""

for arg in "$@"; do
  case "$arg" in
    --skip-sync)      SKIP_SYNC=true ;;
    --skip-firewall)  SKIP_FIREWALL=true ;;
    --skip-nomad)     SKIP_NOMAD=true ;;
    --my-ip)          shift; MY_IP="${1:-}" ;;
    --my-ip=*)        MY_IP="${arg#--my-ip=}" ;;
  esac
done

# Auto-detect public IP if not supplied
if [[ -z "$MY_IP" ]]; then
  MY_IP="$(curl -fsS https://checkip.amazonaws.com || curl -fsS https://icanhazip.com)"
  MY_IP="${MY_IP%/32}"
fi
MY_CIDR="${MY_IP}/32"

SRC_SERVICES="${ROOT_DIR}/services"
REMOTE_SERVICES="/home/${SSH_USER}/platform-docs/services"
REMOTE_VENV="/home/${SSH_USER}/fc-agent-venv"
REMOTE_SRC_DIR="/home/${SSH_USER}/platform-docs-runtime/sandbox-worker/src"
REMOTE_JOB="/tmp/platform-api.nomad"

echo "=== Deploy full platform stack → GCP Nomad ==="
echo "  Project:   $PROJECT_ID / $ZONE / $NOMAD_NAME"
echo "  My IP:     $MY_CIDR"
echo "  Skip sync: $SKIP_SYNC | skip firewall: $SKIP_FIREWALL | skip nomad: $SKIP_NOMAD"
echo ""

# ── Step 1: Sync services/ ───────────────────────────────────────────────────
if [[ "$SKIP_SYNC" == "false" ]]; then
  echo "[1/4] Syncing services/ to VM..."

  # Ensure remote directory exists
  "$GCLOUD_BIN" compute ssh \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    "$NOMAD_NAME" \
    --quiet \
    --command="mkdir -p '${REMOTE_SERVICES}'"

  # Sync the services tree
  "$GCLOUD_BIN" compute scp \
    --recurse \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    "${SRC_SERVICES}/." \
    "${NOMAD_NAME}:${REMOTE_SERVICES}/" \
    --quiet

  echo "  done."
else
  echo "[1/4] Skipping services/ sync (--skip-sync)"
fi

echo ""

# ── Step 2: Start all containers ─────────────────────────────────────────────
echo "[2/4] Starting docker compose stack on VM..."

"$GCLOUD_BIN" compute ssh \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  "$NOMAD_NAME" \
  --quiet \
  --command="$(cat <<'REMOTE'
set -euo pipefail

SERVICES_DIR="${HOME}/platform-docs/services"

# docker compose v2 check
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' (v2) not found. Install docker-compose-plugin." >&2
  exit 1
fi

echo "  Bringing up all services..."
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
    if not line:
        continue
    try:
        rows.append(json.loads(line))
    except Exception:
        pass
bad = [r.get('Name','?') for r in rows if r.get('Health','') not in ('healthy','')]
print(' '.join(bad))
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
REMOTE
)"

echo ""

# ── Step 3: Open firewall ports ───────────────────────────────────────────────
if [[ "$SKIP_FIREWALL" == "false" ]]; then
  echo "[3/4] Opening firewall ports for your IP ($MY_CIDR)..."

  # Ports to expose: Nomad UI, Consul UI, Jaeger UI, MinIO console, platform-api
  # We create/update a single rule scoped to the user's IP.
  RULE_NAME="platform-dev-access"

  if "$GCLOUD_BIN" compute firewall-rules describe "$RULE_NAME" \
      --project="$PROJECT_ID" \
      --format="value(name)" >/dev/null 2>&1; then
    echo "  Updating existing rule: $RULE_NAME"
    "$GCLOUD_BIN" compute firewall-rules update "$RULE_NAME" \
      --project="$PROJECT_ID" \
      --source-ranges="$MY_CIDR" \
      --allow="tcp:4646,tcp:8500,tcp:8080,tcp:9001,tcp:16686,tcp:4317,tcp:4318" \
      --quiet
  else
    echo "  Creating rule: $RULE_NAME"
    "$GCLOUD_BIN" compute firewall-rules create "$RULE_NAME" \
      --project="$PROJECT_ID" \
      --direction=INGRESS \
      --priority=1000 \
      --network=default \
      --action=ALLOW \
      --rules="tcp:4646,tcp:8500,tcp:8080,tcp:9001,tcp:16686,tcp:4317,tcp:4318" \
      --source-ranges="$MY_CIDR" \
      --target-tags=nomad \
      --description="Platform dev UI access — Nomad/Consul/Jaeger/MinIO/API" \
      --quiet
  fi

  echo "  Firewall rule applied."
  echo ""
  echo "  Dashboard URLs (may take 30s to be reachable):"
  VM_IP="34.143.174.106"
  echo "    Nomad:   http://${VM_IP}:4646"
  echo "    Consul:  http://${VM_IP}:8500"
  echo "    Jaeger:  http://${VM_IP}:16686"
  echo "    MinIO:   http://${VM_IP}:9001  (user: minioadmin / minioadmin)"
  echo "    API:     http://${VM_IP}:${API_PORT}/health"
else
  echo "[3/4] Skipping firewall update (--skip-firewall)"
fi

echo ""

# ── Step 4: Redeploy platform-api with full env ───────────────────────────────
if [[ "$SKIP_NOMAD" == "false" ]]; then
  echo "[4/4] Redeploying platform-api Nomad job with full env..."

  remote_script="$(mktemp)"
  cat >"${remote_script}" <<EOF
set -euo pipefail

SSH_USER="${SSH_USER}"
SNAPSHOT_NAME="${SNAPSHOT_NAME}"
API_PORT="${API_PORT}"
FC_POOL_SIZE="${FC_POOL_SIZE}"
REMOTE_SRC_DIR="${REMOTE_SRC_DIR}"
REMOTE_VENV="${REMOTE_VENV}"
REMOTE_JOB="${REMOTE_JOB}"

test -x "\${REMOTE_VENV}/bin/python" || {
  echo "ERROR: missing python venv: \${REMOTE_VENV}" >&2
  exit 1
}

# Stop existing job and kill orphan FC processes
NOMAD_ADDR=http://127.0.0.1:4646 nomad job stop -purge platform-api >/dev/null 2>&1 || true
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

        # Observability
        OTEL_ENABLED                = "true"
        OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"

        # Consul
        CONSUL_ENABLED = "true"
        CONSUL_HOST    = "127.0.0.1"
        CONSUL_PORT    = "8500"

        # PostgreSQL
        DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/platform"

        # Redis
        REDIS_URL = "redis://127.0.0.1:6379/0"
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

  "$GCLOUD_BIN" compute ssh \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    "$NOMAD_NAME" \
    --quiet \
    --command='bash -s' < "${remote_script}"

  rm -f "${remote_script}"

  echo ""
  echo "  platform-api redeployed with full env."
else
  echo "[4/4] Skipping Nomad redeploy (--skip-nomad)"
fi

echo ""
echo "=== Done. Full stack is up. ==="
VM_IP="34.143.174.106"
echo ""
echo "  Nomad:   http://${VM_IP}:4646"
echo "  Consul:  http://${VM_IP}:8500"
echo "  Jaeger:  http://${VM_IP}:16686"
echo "  MinIO:   http://${VM_IP}:9001  (minioadmin / minioadmin)"
echo "  API:     http://${VM_IP}:${API_PORT}/health"
echo ""
echo "  Run smoke test:"
echo "    $(dirname "$0")/../smoke-test.sh http://${VM_IP}:${API_PORT}"
