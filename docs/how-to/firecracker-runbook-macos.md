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

Expected — all three show `healthy`:

```
NAME        STATUS
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

Troubleshoot: if MinIO is unreachable, confirm Docker Desktop is running and `docker compose ps` shows port `9000->9000`.

---

## 4. Build a snapshot from scratch (sim mode)

In sim mode there is no real VM. A "snapshot" is three files uploaded to MinIO:
- `vmstate.bin` — dummy binary (placeholder for VM state)
- `memory.bin` — dummy binary (placeholder for VM memory)
- `meta.json` — JSON metadata the fc-agent reads on startup

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

> **Known issue:** The `fc-agent` entry point currently fails to start because the `agents` package is not yet present in `src/`. Running `fc-agent` will produce `ModuleNotFoundError: No module named 'agents'`. Section 5 documents the intended workflow for when the package is available. To verify snapshot download now, you can exercise `SnapshotStore` directly via the platform API (see section 7).

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
