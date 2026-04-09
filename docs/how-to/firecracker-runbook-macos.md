# Firecracker Runbook — macOS (Sim Mode)

| Field | Value |
|---|---|
| Platform | macOS (Apple Silicon or Intel) |
| Firecracker mode | `sim` — no KVM required, mock VM output |
| Last updated | 2026-04-10 |

This runbook covers: repo setup → infrastructure → build a Firecracker snapshot (mock) → load an existing snapshot → deploy a Nomad job → run Python code via the platform API.

---

## 1. Prerequisites

Install these before starting:

```bash
# Python 3.12+
python3 --version   # must print 3.12.x or later

# Docker Desktop (includes docker compose v2)
docker --version
docker compose version

# uv — fast Python package installer
brew install uv

# jq — JSON pretty-printer for curl responses
brew install jq

# Nomad CLI
brew tap hashicorp/tap
brew install hashicorp/tap/nomad
nomad version   # must print Nomad v1.x

# MinIO client mc (needed to upload snapshot files)
brew install minio/stable/mc
```

**Not needed on macOS:** firecracker binary, KVM, jailer.

---

## 2. Clone and install

```bash
git clone <repo-url>
cd platform-docs/sandbox-worker

uv venv .venv
source .venv/bin/activate

uv pip install -e ".[dev]"
```

Verify:

```bash
which platform-api   # confirm entry point is installed
pytest --collect-only -q 2>&1 | tail -10   # must show collected tests, no errors
```

Troubleshoot: if `platform-api: command not found`, ensure the venv is activated (`source .venv/bin/activate`).

> **Known issue:** The `fc-agent`, `wasm-agent`, and `gui-agent` entry points are registered in `pyproject.toml` but will fail immediately on invocation because the `agents` package (`src/agents/`) does not yet exist. Only `platform-api` is functional. Do not attempt to run the other entry points directly.

---

## 3. Start infrastructure

Run from the `services/` directory:

> **Note:** Do not use `make infra-up` from `sandbox-worker/` — the Makefile target runs `docker compose up -d` relative to `sandbox-worker/` which has no compose file. Use the manual path below.

```bash
cd ../services
docker compose up -d
```

Verify all three services are healthy:

```bash
# Still in services/
docker compose ps
```

Expected — five services total. Data and controller services show `healthy`; jaeger has no healthcheck so it shows `Up` only:

```
NAME        STATUS
consul      Up (healthy)
jaeger      Up
minio       Up (healthy)
postgres    Up (healthy)
redis       Up (healthy)
```

Start the platform API (in a separate terminal, from `sandbox-worker/`):

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=sim \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  platform-api
```

Verify health:

```bash
curl -s http://localhost:8080/health | jq
```

Expected:

```json
{
  "status": "healthy",
  "version": "0.2.0",
  "services": {
    "vm_pool": "healthy (pool_size=2)"
  }
}
```
>
> **Known issue:** current `platform-api` startup still has VM-pool warmup wiring issues. If the process exits before `/health` is available, treat section 3 as the intended workflow and continue with sections 4-5 to validate snapshot artifacts directly.

Troubleshoot: if MinIO is unreachable, confirm Docker Desktop is running and `docker compose ps` shows port `9000->9000`.

---

## 4. Build a snapshot from scratch (sim mode)

In sim mode there is no real VM. A "snapshot" is three files uploaded to MinIO:
- `vmstate.bin` — dummy binary (placeholder for VM state)
- `memory.bin` — dummy binary (placeholder for VM memory)
- `meta.json` — JSON metadata the fc-agent reads on startup

Recommended for this repo: use the helper scripts in `tools/snapshot-builder/`. They create local placeholder artifacts with the current repo layout:
- local files: `<out-dir>/<name>/state`, `mem`, `meta.json`
- uploaded objects: `<name>/vmstate.bin`, `memory.bin`, `meta.json`

Run from the repo root (`platform-docs/`):

```bash
tools/snapshot-builder/test/test-snapshot-builder.sh

export SNAPSHOT_OUT_DIR=/tmp/snapshots
export SNAPSHOT_CACHE_DIR=/tmp/snapshot-cache

bash tools/snapshot-builder/snapshot-builder.sh \
  --name python-v1 \
  --skip-snapshot \
  --skip-upload

bash tools/snapshot-builder/upload-minio.sh \
  --snapshot-dir /tmp/snapshots/python-v1 \
  --name python-v1 \
  --rootfs /tmp/snapshot-cache/python-v1.ext4 \
  --endpoint http://localhost:9000

mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local/platform-snapshots/python-v1/
```

> On macOS, `snapshot-builder.sh` automatically falls back to a placeholder rootfs build and `--skip-snapshot` creates dummy `state`/`mem` files for upload testing.
>
> Do not use `make snapshot-create` on macOS. That target invokes the real Firecracker snapshot path, which requires Linux + KVM.

The manual object-creation flow below is still useful if you want to inspect the uploaded files directly.

**4a. Create the MinIO bucket**

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/platform-snapshots || true
```

Expected: `Bucket created successfully \`local/platform-snapshots\``.

**4b. Create the snapshot files locally**

```bash
mkdir -p /tmp/python-v1

# Dummy binaries (real Firecracker would write actual VM state here)
dd if=/dev/zero bs=1k count=4 2>/dev/null | gzip > /tmp/python-v1/vmstate.bin
dd if=/dev/zero bs=1k count=4 2>/dev/null | gzip > /tmp/python-v1/memory.bin

# Metadata that fc-agent reads
cat > /tmp/python-v1/meta.json <<'EOF'
{
  "name": "python-v1",
  "version": "3.12",
  "kernel": "vmlinux-5.10",
  "rootfs": "python-v1.ext4",
  "vcpus": 2,
  "mem_mib": 512,
  "dry_run": true,
  "files": {}
}
EOF
```

**4c. Upload the snapshot to MinIO**

```bash
mc cp /tmp/python-v1/vmstate.bin local/platform-snapshots/python-v1/vmstate.bin
mc cp /tmp/python-v1/memory.bin  local/platform-snapshots/python-v1/memory.bin
mc cp /tmp/python-v1/meta.json   local/platform-snapshots/python-v1/meta.json
```

Verify upload:

```bash
mc ls local/platform-snapshots/python-v1/
```

Expected (three objects):

```
[...] vmstate.bin
[...] memory.bin
[...] meta.json
```

Troubleshoot: if `mc alias set` fails, check MinIO is up (`docker compose ps` from `services/`) and credentials match `minioadmin`/`minioadmin`.

---

## 5. Load an existing snapshot from MinIO

`SnapshotStore.ensure()` downloads from MinIO to a local cache on first access, then serves from disk on subsequent requests. The cache dir is `SNAPSHOT_CACHE_DIR` (default `/var/sandbox/cache`).

> **Known issue:** The `fc-agent` entry point currently fails to start because the `agents` package is not yet present in `src/`. Running `fc-agent` will produce `ModuleNotFoundError: No module named 'agents'`. Section 5 documents the intended workflow for when the package is available.
>
> **Current limitation:** there is no standalone HTTP endpoint that forces a named snapshot download independently of the VM pool startup path. Until `fc-agent` startup is repaired, the practical verification available today is `mc ls` for the uploaded objects plus local-cache inspection once the runtime path is fixed.

**5a. Start fc-agent with snapshot env vars**

In a new terminal (from `sandbox-worker/`):

```bash
source .venv/bin/activate
FC_MODE=sim \
  SNAPSHOT_NAME=python-v1 \
  SNAPSHOT_CACHE_DIR=/tmp/sandbox-cache \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  MINIO_BUCKET=platform-snapshots \
  fc-agent
```

Expected log line on first start (structlog output):

```
snapshot not cached, downloading from MinIO  name=python-v1
```

On second start (cache hit):

```
snapshot cache hit  name=python-v1
```

> **Note:** The cache-hit message is `debug` level. It only appears if debug logging is enabled (e.g., set `LOG_LEVEL=debug` as an additional env var). With default log config, no snapshot log line will appear on cache hit — this is expected.

**5b. Verify local cache**

```bash
ls /tmp/sandbox-cache/python-v1/
```

Expected:

```
memory.bin  meta.json  vmstate.bin
```

Troubleshoot: if download fails with an error about `mc` not found in PATH, the `SnapshotStore` falls back to HTTP download directly from `MINIO_ENDPOINT`. Ensure MinIO is reachable at `http://localhost:9000`.

---

## 6. Deploy the Nomad job

**6a. Start a local single-node Nomad dev cluster**

In a new terminal:

```bash
sudo nomad agent -dev \
  -bind=0.0.0.0 \
  -network-interface=lo0
```

Wait for `Nomad agent started!` in output, then verify:

```bash
nomad node status
```

Expected: one node with status `ready`.

**6b. Adjust the job for local dev**

The debug job at `services/controller/nomad/jobs/debug-python-runtime.nomad` uses `raw_exec` with `command = "/usr/local/bin/fc-agent"`. On macOS the binary lives in your venv, not `/usr/local/bin/`. Create a local override:

> Run from the repo root (`platform-docs/`), not from inside `sandbox-worker/`.

```bash
VENV_PATH=$(pwd)/sandbox-worker/.venv

cat > /tmp/sandbox-worker-macos.nomad <<EOF
job "sandbox-worker-macos" {
  datacenters = ["dc1"]
  type        = "service"

  group "fc-agent" {
    count = 1

    task "fc-agent" {
      driver = "raw_exec"

      config {
        command = "${VENV_PATH}/bin/fc-agent"
      }

      env {
        FC_MODE            = "sim"
        SNAPSHOT_NAME      = "python-v1"
        SNAPSHOT_CACHE_DIR = "/tmp/sandbox-cache"
        MINIO_ENDPOINT     = "http://127.0.0.1:9000"
        MINIO_ACCESS_KEY   = "minioadmin"
        MINIO_SECRET_KEY   = "minioadmin"
        MINIO_BUCKET       = "platform-snapshots"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
EOF
```

> **Known issue:** `fc-agent` currently fails to start (missing `agents` module — see section 5 warning). The Nomad allocation will show `failed`. This section documents the intended deployment workflow.

**6c. Run the job**

```bash
nomad job run /tmp/sandbox-worker-macos.nomad
```

Expected:

```
==> Monitoring evaluation "..."
    Allocation "..." created: node "...", group "fc-agent"
    Evaluation status changed: "pending" -> "complete"
==> Evaluation complete
```

**6d. Check allocation status**

```bash
nomad job status sandbox-worker-macos
```

Expected: `Status = running` (or `failed` if fc-agent module issue is not resolved).

View logs:

```bash
ALLOC_ID=$(nomad job status sandbox-worker-macos | awk '/^Allocations/,0 { if (NR>1 && ($6=="running" || $6=="failed")) print $1 }' | head -1)
nomad alloc logs $ALLOC_ID fc-agent
```

Troubleshoot: if `raw_exec` driver is disabled, add `plugin "raw_exec" { config { enabled = true } }` to your Nomad config or use `-dev` mode which enables it by default.

---

## 7. Run Python code end-to-end

> **Known issue:** `POST /execute` currently fails with HTTP 500 due to a code bug: `ExecutionService.execute()` calls `vm.run(job)` but `FirecrackerVM` only exposes `.execute(tool, input_data)`. The steps below document the intended workflow. To test the API layer without the VM, use `POST /sessions` and `GET /health` which do not invoke the VM pool.

> **Note:** This section uses the `platform-api` directly. The fc-agent Nomad deployment in section 6 is separate — `platform-api` has its own in-process VM lifecycle manager and does not depend on the Nomad-deployed fc-agent to handle API requests.

**7a. Ensure platform-api is running**

From section 3, `platform-api` should be running in a terminal with `FC_MODE=sim`. If not, restart it:

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=sim \
  SNAPSHOT_NAME=python-v1 \
  SNAPSHOT_CACHE_DIR=/tmp/sandbox-cache \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  MINIO_BUCKET=platform-snapshots \
  platform-api
```

**7b. Create a session**

```bash
SESSION=$(curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}' | jq -r '.session_id')
echo "Session: $SESSION"
```

Expected: `Session: <uuid>` (e.g. `3f7b2c1d-e4f5-...`)

**7c. Execute Python code**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"print('hello from sandbox')\"}
  }" | jq
```

> **Current behavior (before bug fix):** Returns HTTP 500 with `AttributeError: 'FirecrackerVM' object has no attribute 'run'`.
>
> **Intended behavior (after bug fix):** Returns JSON with `status: "completed"` and sim-mode output:
```json
{
  "job_id": "...",
  "session_id": "...",
  "status": "completed",
  "output": "{\n  \"tool\": \"python_run\",\n  ...\n  \"output\": {\"stdout\": \"[sim] print('hello from sandbox')\\n=> hello from Python\", \"exit_code\": 0}\n}",
  "error_message": "",
  "duration_ms": 5
}
```

**7d. Execute with computation**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"result = sum(range(1000000)); print(f'Sum: {result}')\"}
  }" | jq '.output'
```

> **Note:** In sim mode, the runtime always returns the `[sim] ... => hello from Python` template regardless of the actual code input. The `sum(range(...))` computation is not evaluated — sim mode does not execute Python code inside a VM.

---

## 8. Cleanup

Stop the Nomad job:

```bash
nomad job stop sandbox-worker-macos
```

Stop `platform-api` (Ctrl+C in its terminal, or):

```bash
pkill -f "platform-api"
```

Stop infrastructure:

```bash
cd services
docker compose down
```

Stop the Nomad dev agent (Ctrl+C in its terminal, or):

```bash
sudo pkill nomad
```

Remove local snapshot cache and temp files:

```bash
rm -rf /tmp/sandbox-cache /tmp/python-v1 /tmp/sandbox-worker-macos.nomad
```

Remove MinIO snapshot:

```bash
mc rm --recursive --force local/platform-snapshots/python-v1
```
