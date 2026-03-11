#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${EXAMPLE_DIR}/../.." && pwd)"
PLATFORM_DIR="${REPO_ROOT}/sandbox-platform"
SNAPSHOT_CONFIG="${SNAPSHOT_CONFIG:-${EXAMPLE_DIR}/python-runtime.env}"
JOB_TEMPLATE="${JOB_TEMPLATE:-${EXAMPLE_DIR}/sandbox-python.nomad.hcl.tpl}"
USER_SNAPSHOT_NAME="${SNAPSHOT_NAME:-}"

NOMAD_ADDR="${NOMAD_ADDR:-http://127.0.0.1:4646}"
API_URL="${API_URL:-http://127.0.0.1:8080}"
NOMAD_DATACENTER="${NOMAD_DATACENTER:-dc1}"
NOMAD_NODE_CLASS="${NOMAD_NODE_CLASS:-mixed}"

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://127.0.0.1:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_BUCKET="${MINIO_BUCKET:-platform-snapshots}"

FC_KERNEL_PATH="${FC_KERNEL_PATH:-/opt/platform/test-assets/vmlinux-hello}"
DOWNLOAD_KERNEL="${DOWNLOAD_KERNEL:-false}"

if [[ -f "${SNAPSHOT_CONFIG}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${SNAPSHOT_CONFIG}"
  set +a
fi

SNAPSHOT_NAME="${USER_SNAPSHOT_NAME:-${SNAPSHOT_NAME:-python-runtime-example}}"
SNAPSHOT_OUT_DIR="${SNAPSHOT_OUT_DIR:-${PLATFORM_DIR}/bin/example-snapshots}"
SNAPSHOT_CACHE_DIR="${SNAPSHOT_CACHE_DIR:-${PLATFORM_DIR}/bin/example-snapshot-cache}"

JOB_NAME="${JOB_NAME:-python-runtime-sandbox-$(date +%s)}"
JOB_FILE="${PLATFORM_DIR}/bin/${JOB_NAME}.nomad"
PID_DIR="${PLATFORM_DIR}/bin/example-python-runtime"
API_PID_FILE="${PID_DIR}/platform-api.pid"
API_LOG_FILE="${PID_DIR}/platform-api.log"
FC_AGENT_BIN="${FC_AGENT_BIN:-${PLATFORM_DIR}/bin/fc-agent}"

STARTED_NOMAD=0
STARTED_COMPOSE=0
STARTED_API=0
JOB_DEPLOYED=0
GENERATED_SNAPSHOT=0
SELECTED_FC_MODE=""

log() {
  printf '[python-runtime-example] %s\n' "$*"
}

warn() {
  printf '[python-runtime-example] warning: %s\n' "$*" >&2
}

die() {
  printf '[python-runtime-example] error: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

json_string() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

json_field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1" 2>/dev/null
}

health_ok() {
  curl -sf "${API_URL}/health" >/dev/null 2>&1
}

managed_nomad_pidfiles_exist() {
  [[ -f "${PLATFORM_DIR}/bin/nomad-server.pid" ]] || [[ -f "${PLATFORM_DIR}/bin/nomad-client1.pid" ]] || [[ -f "${PLATFORM_DIR}/bin/nomad-client2.pid" ]]
}

stop_managed_nomad_cluster() {
  local pidfile
  for pidfile in \
    "${PLATFORM_DIR}/bin/nomad-server.pid" \
    "${PLATFORM_DIR}/bin/nomad-client1.pid" \
    "${PLATFORM_DIR}/bin/nomad-client2.pid"; do
    if [[ -f "${pidfile}" ]]; then
      kill "$(cat "${pidfile}")" >/dev/null 2>&1 || true
      rm -f "${pidfile}"
    fi
  done
}

wait_for_http() {
  local url="$1"
  local attempts="${2:-30}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if curl -sf "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cleanup() {
  if [[ "${JOB_DEPLOYED}" -eq 1 ]]; then
    NOMAD_ADDR="${NOMAD_ADDR}" nomad job stop -purge -yes "${JOB_NAME}" >/dev/null 2>&1 || true
  fi

  if [[ "${STARTED_API}" -eq 1 && -f "${API_PID_FILE}" ]]; then
    kill "$(cat "${API_PID_FILE}")" >/dev/null 2>&1 || true
  fi

  if [[ "${STARTED_COMPOSE}" -eq 1 ]]; then
    (
      cd "${PLATFORM_DIR}"
      docker compose down >/dev/null 2>&1 || true
    )
  fi

  if [[ "${STARTED_NOMAD}" -eq 1 ]]; then
    local pidfile
    for pidfile in \
      "${PLATFORM_DIR}/bin/nomad-server.pid" \
      "${PLATFORM_DIR}/bin/nomad-client1.pid" \
      "${PLATFORM_DIR}/bin/nomad-client2.pid"; do
      if [[ -f "${pidfile}" ]]; then
        kill "$(cat "${pidfile}")" >/dev/null 2>&1 || true
      fi
    done
  fi

  if [[ "${GENERATED_SNAPSHOT}" -eq 1 ]]; then
    rm -rf "${SNAPSHOT_OUT_DIR:?}/${SNAPSHOT_NAME}" || true
    rm -rf "${SNAPSHOT_CACHE_DIR:?}/${SNAPSHOT_NAME}" || true
    rm -f "${SNAPSHOT_CACHE_DIR}/${SNAPSHOT_NAME}.ext4" || true
  fi

  rm -f "${JOB_FILE}" || true
  rm -rf "${PID_DIR}" || true
}

trap cleanup EXIT

detect_fc_mode() {
  if [[ -n "${FC_MODE:-}" ]]; then
    printf '%s\n' "${FC_MODE}"
    return 0
  fi

  if [[ "$(uname -s)" == "Linux" && -e /dev/kvm ]] && command -v firecracker >/dev/null 2>&1; then
    printf 'real\n'
    return 0
  fi

  printf 'sim\n'
}

prepare_snapshot_assets() {
  local snapshot_dir cache_dir

  mkdir -p "${SNAPSHOT_OUT_DIR}" "${SNAPSHOT_CACHE_DIR}"
  GENERATED_SNAPSHOT=1
  SELECTED_FC_MODE="$(detect_fc_mode)"
  snapshot_dir="${SNAPSHOT_OUT_DIR}/${SNAPSHOT_NAME}"
  cache_dir="${SNAPSHOT_CACHE_DIR}/${SNAPSHOT_NAME}"

  log "Preparing Firecracker assets (mode=${SELECTED_FC_MODE}, snapshot=${SNAPSHOT_NAME})"

  if [[ "${SELECTED_FC_MODE}" == "real" ]]; then
    if [[ -f "${FC_KERNEL_PATH}" ]]; then
      if ! (
        cd "${REPO_ROOT}"
        SNAPSHOT_CACHE_DIR="${SNAPSHOT_CACHE_DIR}" \
        SNAPSHOT_OUT_DIR="${SNAPSHOT_OUT_DIR}" \
        MINIO_ENDPOINT="${MINIO_ENDPOINT}" \
        MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY}" \
        MINIO_SECRET_KEY="${MINIO_SECRET_KEY}" \
        MINIO_BUCKET="${MINIO_BUCKET}" \
        tools/snapshot-builder/snapshot-builder.sh \
          --config "${SNAPSHOT_CONFIG}" \
          --kernel "${FC_KERNEL_PATH}" \
          --skip-upload
      ); then
        warn "real snapshot build failed; falling back to sim assets"
        SELECTED_FC_MODE="sim"
      fi
    elif [[ "${DOWNLOAD_KERNEL}" == "true" ]]; then
      if ! (
        cd "${REPO_ROOT}"
        SNAPSHOT_CACHE_DIR="${SNAPSHOT_CACHE_DIR}" \
        SNAPSHOT_OUT_DIR="${SNAPSHOT_OUT_DIR}" \
        MINIO_ENDPOINT="${MINIO_ENDPOINT}" \
        MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY}" \
        MINIO_SECRET_KEY="${MINIO_SECRET_KEY}" \
        MINIO_BUCKET="${MINIO_BUCKET}" \
        tools/snapshot-builder/snapshot-builder.sh \
          --config "${SNAPSHOT_CONFIG}" \
          --download-kernel \
          --skip-upload
      ); then
        warn "kernel download or snapshot build failed; falling back to sim assets"
        SELECTED_FC_MODE="sim"
      fi
    else
      warn "FC_KERNEL_PATH not found at ${FC_KERNEL_PATH}; using sim assets"
      SELECTED_FC_MODE="sim"
    fi
  fi

  if [[ "${SELECTED_FC_MODE}" == "sim" ]]; then
    (
      cd "${REPO_ROOT}"
      SNAPSHOT_CACHE_DIR="${SNAPSHOT_CACHE_DIR}" \
      SNAPSHOT_OUT_DIR="${SNAPSHOT_OUT_DIR}" \
      MINIO_ENDPOINT="${MINIO_ENDPOINT}" \
      MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY}" \
      MINIO_SECRET_KEY="${MINIO_SECRET_KEY}" \
      MINIO_BUCKET="${MINIO_BUCKET}" \
      tools/snapshot-builder/snapshot-builder.sh \
        --config "${SNAPSHOT_CONFIG}" \
        --skip-snapshot \
        --skip-upload \
        --dry-run
    )
  fi

  [[ -f "${snapshot_dir}/state" ]] || die "snapshot state not found: ${snapshot_dir}/state"
  [[ -f "${snapshot_dir}/mem" ]] || die "snapshot memory not found: ${snapshot_dir}/mem"
  [[ -f "${snapshot_dir}/meta.json" ]] || die "snapshot metadata not found: ${snapshot_dir}/meta.json"

  mkdir -p "${cache_dir}"
  cp "${snapshot_dir}/state" "${cache_dir}/vmstate.bin"
  cp "${snapshot_dir}/mem" "${cache_dir}/memory.bin"
  cp "${snapshot_dir}/meta.json" "${cache_dir}/meta.json"
}

render_nomad_job() {
  [[ -f "${JOB_TEMPLATE}" ]] || die "job template not found: ${JOB_TEMPLATE}"

  sed \
    -e "s|__JOB_NAME__|${JOB_NAME}|g" \
    -e "s|__DATACENTER__|${NOMAD_DATACENTER}|g" \
    -e "s|__NODE_CLASS__|${NOMAD_NODE_CLASS}|g" \
    -e "s|__FC_AGENT_BIN__|${FC_AGENT_BIN}|g" \
    -e "s|__FC_MODE__|${SELECTED_FC_MODE}|g" \
    -e "s|__SNAPSHOT_NAME__|${SNAPSHOT_NAME}|g" \
    -e "s|__SNAPSHOT_CACHE_DIR__|${SNAPSHOT_CACHE_DIR}|g" \
    -e "s|__MINIO_ENDPOINT__|${MINIO_ENDPOINT}|g" \
    -e "s|__MINIO_ACCESS_KEY__|${MINIO_ACCESS_KEY}|g" \
    -e "s|__MINIO_SECRET_KEY__|${MINIO_SECRET_KEY}|g" \
    -e "s|__MINIO_BUCKET__|${MINIO_BUCKET}|g" \
    "${JOB_TEMPLATE}" > "${JOB_FILE}"
}

run_smoke_test() {
  local attempt session_resp session_id exec_resp status output request_body
  local code='print("hello from Nomad Firecracker")'
  local code_json

  code_json="$(printf '%s' "${code}" | json_string)"

  for attempt in $(seq 1 15); do
    session_resp="$(curl -sf -X POST "${API_URL}/sessions" \
      -H "Content-Type: application/json" \
      -d '{"runtime":"microvm"}' 2>/dev/null || true)"
    session_id="$(printf '%s' "${session_resp}" | json_field session_id || true)"

    if [[ -z "${session_id}" ]]; then
      sleep 2
      continue
    fi

    request_body="{\"session_id\":\"${session_id}\",\"tool\":\"python_run\",\"input\":{\"code\":${code_json}}}"

    exec_resp="$(curl -sf -X POST "${API_URL}/execute" \
      -H "Content-Type: application/json" \
      -d "${request_body}" \
      2>/dev/null || true)"
    status="$(printf '%s' "${exec_resp}" | json_field status || true)"
    output="$(printf '%s' "${exec_resp}" | json_field output || true)"

    if [[ "${status}" == "completed" && "${output}" == *"hello from Nomad Firecracker"* ]]; then
      log "Smoke test passed on attempt ${attempt}"
      log "Execution output: ${output}"
      return 0
    fi

    sleep 2
  done

  die "python_run smoke test did not complete successfully"
}

main() {
  require_cmd curl
  require_cmd docker
  require_cmd go
  require_cmd make
  require_cmd nomad
  require_cmd python3

  docker compose version >/dev/null 2>&1 || die "docker compose is required"
  mkdir -p "${PID_DIR}"

  if managed_nomad_pidfiles_exist; then
    log "Stopping repo-managed Nomad cluster from existing pidfiles"
    stop_managed_nomad_cluster
  fi

  if NOMAD_ADDR="${NOMAD_ADDR}" nomad node status >/dev/null 2>&1; then
    log "Reusing existing Nomad cluster at ${NOMAD_ADDR}"
  else
    log "Starting local Nomad cluster"
    STARTED_NOMAD=1
    (
      cd "${PLATFORM_DIR}"
      ./scripts/start-nomad-cluster.sh
    )
  fi

  log "Building sandbox-platform binaries"
  (
    cd "${PLATFORM_DIR}"
    make build
  )

  if [[ ! -x "${FC_AGENT_BIN}" ]]; then
    die "fc-agent binary not found after build: ${FC_AGENT_BIN}"
  fi

  if [[ "$(
    cd "${PLATFORM_DIR}"
    docker compose ps --status running --services 2>/dev/null | wc -l | tr -d ' '
  )" == "0" ]]; then
    STARTED_COMPOSE=1
  fi

  log "Ensuring PostgreSQL, Redis, and MinIO are running"
  (
    cd "${PLATFORM_DIR}"
    docker compose up -d
  )

  prepare_snapshot_assets
  render_nomad_job

  log "Submitting Nomad job ${JOB_NAME}"
  NOMAD_ADDR="${NOMAD_ADDR}" nomad job run "${JOB_FILE}"
  JOB_DEPLOYED=1

  if health_ok; then
    log "Reusing existing platform-api at ${API_URL}"
  else
    log "Starting platform-api"
    (
      cd "${PLATFORM_DIR}"
      "${PLATFORM_DIR}/bin/platform-api" > "${API_LOG_FILE}" 2>&1 &
      echo $! > "${API_PID_FILE}"
    )
    STARTED_API=1
    wait_for_http "${API_URL}/health" 30 || die "platform-api did not become healthy"
  fi

  run_smoke_test
  log "Example complete. Cleanup is running."
}

main "$@"
