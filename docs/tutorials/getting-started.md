# Getting Started with Sandbox Platform

| Field | Value |
|---|---|
| Status | Active |
| Audience | New contributors, integrators |
| Scope | First-run tutorial: install, start, execute a job, upload an artifact |
| Last updated | April 8, 2026 |

## What the platform does

Sandbox Platform runs untrusted workloads in isolated environments. It routes each job to the right execution tier based on the tool requested:

| Runtime | Use case | Startup |
|---|---|---|
| WASM | Fast, stateless tool execution | < 5 ms |
| Firecracker microVM | Secure compute for untrusted code | 20–80 ms from snapshot |
| GUI (Chromium) | Browser automation and visual workflows | ~300 ms warm |

The platform exposes a single HTTP API. Callers create a session, submit an execution request, and receive structured output. Artifacts, snapshots, and package wheels are stored in MinIO and survive the sandbox lifecycle.

---

## Step 1 — Install prerequisites

**Python 3.12+**

```bash
python3 --version   # must be 3.12 or later
```

**Docker and Docker Compose** (for local infrastructure)

```bash
docker --version
docker compose version
```

**System packages** (macOS)

```bash
brew install jq
```

---

## Step 2 — Clone and install

```bash
git clone <repo-url>
cd platform-docs/sandbox-platform

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package and dev dependencies
pip install -e ".[dev]"
```

Verify the install:

```bash
platform-api --help      # should print uvicorn startup help
pytest --collect-only    # should collect 235 tests
```

---

## Step 3 — Start infrastructure

```bash
make dev
```

This starts PostgreSQL, Redis, and MinIO via Docker Compose, then launches:

- `platform-api` on port `8080`
- `fc-agent` (Firecracker runtime worker)
- `wasm-agent` (WASM runtime worker)
- `gui-agent` (GUI runtime worker)

---

## Step 4 — Check platform health

```bash
curl -s http://localhost:8080/health | jq
```

Expected response when all services are up:

```json
{
  "status": "healthy",
  "version": "0.1.0-local",
  "services": {
    "postgres": "healthy",
    "redis": "healthy"
  }
}
```

If any service is unhealthy, the status field returns `"degraded"` and the HTTP status is `503`.

---

## Step 5 — Create a session

Sessions bind a series of requests to a specific runtime tier.

```bash
curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}' | jq
```

Response:

```json
{
  "session_id": "sess_abc123",
  "runtime": "microvm",
  "status": "active"
}
```

Supported runtime values: `wasm`, `microvm`, `gui`. If omitted, the API defaults to `wasm`.

---

## Step 6 — Execute a tool

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_abc123",
    "tool": "python_run",
    "input": {
      "code": "print(\"hello from sandbox\")"
    }
  }' | jq
```

Response:

```json
{
  "job_id": "job_xyz789",
  "status": "completed",
  "output": "hello from sandbox\n",
  "error_message": null,
  "duration_ms": 42
}
```

You can also omit `session_id`. The platform creates a session automatically based on the tool's routing rule.

---

## Step 7 — Upload an artifact

```bash
echo "result data" > output.txt

curl -s -X POST http://localhost:8080/artifacts \
  -F "session_id=sess_abc123" \
  -F "name=output.txt" \
  -F "file=@./output.txt" | jq
```

Response:

```json
{
  "artifact_id": "4f9914c7-2f6d-4636-917c-03c7d987e61e",
  "key": "4f9914c7-2f6d-4636-917c-03c7d987e61e/output.txt",
  "url": "http://localhost:9000/platform-artifacts/4f9914c7-2f6d-4636-917c-03c7d987e61e/output.txt",
  "size": 12
}
```

Download the artifact:

```bash
curl -s http://localhost:8080/artifacts/4f9914c7-2f6d-4636-917c-03c7d987e61e/output.txt
```

---

## Step 8 — Install a package into a session

```bash
curl -s -X POST http://localhost:8080/packages/install \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_abc123",
    "package_name": "numpy",
    "version": "1.26.0"
  }' | jq
```

Response:

```json
{
  "name": "numpy",
  "version": "1.26.0",
  "key": "numpy/1.26.0",
  "status": "installed"
}
```

On subsequent calls for the same package and version, status returns `"cached"`.

---

## Step 9 — Stop the environment

```bash
make stop
```

To also remove build artifacts:

```bash
make clean
```

---

## Local execution modes

The platform detects its environment automatically:

| Condition | Firecracker mode |
|---|---|
| `FC_MODE=real` or `/dev/kvm` present | Real microVM execution (Linux + KVM required) |
| `FC_MODE=sim` or no `/dev/kvm` | Simulation mode — safe on macOS, returns mock output |

WASM and GUI follow the same pattern: real execution when dependencies are present, simulation otherwise.

---

## Optional features

All advanced features are off by default. Enable them with environment variables:

| Feature | Variable | Example |
|---|---|---|
| Consul service discovery | `CONSUL_ENABLED=true` | `CONSUL_ENABLED=true fc-agent` |
| Auto-scaling | `SCALER_ENABLED=true` | `SCALER_ENABLED=true platform-api` |
| Mutual TLS | `MTLS_ENABLED=true` | `MTLS_ENABLED=true platform-api` |

---

## Next steps

| Goal | Document |
|---|---|
| Understand the full system | [../explanation/system-overview.md](../explanation/system-overview.md) |
| See all API endpoints | [../reference/api-spec.md](../reference/api-spec.md) |
| Deploy to a cluster | [../how-to/deploy.md](../how-to/deploy.md) |
| Diagnose problems | [../how-to/troubleshooting.md](../how-to/troubleshooting.md) |
| Understand runtime tiers | [../reference/runtime-reference.md](../reference/runtime-reference.md) |
