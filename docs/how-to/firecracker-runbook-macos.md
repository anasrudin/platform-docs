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
platform-api --help  # prints uvicorn help
pytest --collect-only -q 2>&1 | tail -10   # must show collected tests, no errors
```

Troubleshoot: if `fc-agent: command not found`, ensure the venv is activated (`source .venv/bin/activate`).

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
