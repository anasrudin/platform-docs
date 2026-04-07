# Run Locally

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, operators |
| Scope | Local startup, validation, and shutdown for the Python sandbox environment |
| Last updated | April 8, 2026 |

## Objective

Use this guide to start the local sandbox, validate the core execution flow, and stop the environment cleanly.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | `python3 --version` |
| Docker | any recent | For PostgreSQL, Redis, MinIO |
| Docker Compose | v2+ | `docker compose version` |
| `curl` | any | For manual API testing |
| `jq` | any | For formatted JSON output |

macOS install:

```bash
brew install jq
```

> **Firecracker (optional):** Real microVM execution requires Linux with KVM (`/dev/kvm`). On macOS the runtime falls back to simulation mode automatically — no action needed.

---

## Install

```bash
cd sandbox-platform

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the platform package with dev dependencies
pip install -e ".[dev]"
```

Verify:

```bash
pytest --collect-only   # should show 235 items
platform-api --help     # should print without error
```

---

## Start the sandbox

```bash
make dev
```

This runs `docker compose up` for PostgreSQL, Redis, and MinIO, then starts all four processes:

| Process | Port | Purpose |
|---|---|---|
| `platform-api` | `8080` | Main HTTP API |
| `fc-agent` | `8081` | Firecracker runtime worker + health |
| `wasm-agent` | `8082` | WASM runtime worker + health |
| `gui-agent` | `8083` | GUI runtime worker + health |

---

## Validate the environment

### API health check

```bash
curl -s http://localhost:8080/health | jq
```

Expected:

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

### Agent health checks

```bash
curl -s http://localhost:8081/health | jq   # fc-agent
curl -s http://localhost:8082/health | jq   # wasm-agent
curl -s http://localhost:8083/health | jq   # gui-agent
```

### Run the unit test suite

```bash
pytest
```

All 235 tests should pass without running Docker — they mock all external dependencies.

### End-to-end smoke test

```bash
./test-e2e.sh
```

This validates: health check → session creation → Firecracker execution → WASM execution → GUI execution → artifact upload.

---

## Common commands

| Command | Purpose |
|---|---|
| `make dev` | Start infra + all agents |
| `make run` | Start only `platform-api` (assumes infra already running) |
| `make stop` | Stop all processes and Docker Compose |
| `make clean` | Remove build artifacts and `__pycache__` |
| `pytest` | Run all 235 unit tests |
| `pytest --cov=sandbox_platform` | Run with coverage report |

---

## Optional features

All advanced features are disabled by default. Enable them individually:

### Consul service discovery

Requires a running Consul agent. Start one locally:

```bash
consul agent -dev
```

Then start agents with Consul enabled:

```bash
CONSUL_ENABLED=true fc-agent
CONSUL_ENABLED=true wasm-agent
CONSUL_ENABLED=true gui-agent
```

Verify registration:

```bash
curl -s http://localhost:8500/v1/agent/services | jq 'keys'
```

### Session KV in Consul

Enabled automatically when `CONSUL_ENABLED=true`. Sessions are stored at `sandbox/sessions/{session_id}` in Consul KV. The platform-api also uses the session store when started with Consul enabled:

```bash
CONSUL_ENABLED=true platform-api
```

### Auto-scaler

```bash
SCALER_ENABLED=true platform-api
```

Scaler ticks every 60 seconds by default. To test with a faster interval:

```bash
SCALER_ENABLED=true SCALER_INTERVAL=10 platform-api
```

### Mutual TLS (mTLS)

Requires certificates in `/etc/sandbox/certs/`. For local testing, generate a self-signed CA and cert:

```bash
# CA
openssl ecparam -name P-256 -genkey -noout -out ca.key
openssl req -new -x509 -key ca.key -out ca.crt -days 365 -subj "/CN=sandbox-ca"

# Server cert
openssl ecparam -name P-256 -genkey -noout -out server.key
openssl req -new -key server.key -out server.csr -subj "/CN=platform-api"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365

# Install
sudo mkdir -p /etc/sandbox/certs
sudo cp ca.crt server.crt server.key /etc/sandbox/certs/
```

Then start with mTLS:

```bash
MTLS_ENABLED=true platform-api
```

Requests without a valid client certificate will return HTTP 403.

---

## Execution modes

| Environment | Firecracker mode |
|---|---|
| Linux with `/dev/kvm` | Real microVM execution |
| `FC_MODE=real` | Force real mode (fails without KVM) |
| macOS or `FC_MODE=sim` | Simulation — returns mock output |

WASM and GUI follow the same pattern: real when dependencies are present, simulation otherwise.

---

## Environment variable reference

### Core

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgres://postgres:postgres@localhost:5432/platform?sslmode=disable` | PostgreSQL DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `FC_MODE` | auto-detect | `real` or `sim` |
| `FC_POOL_SIZE` | `2` | Firecracker pre-warmed VM pool size |

### Consul

| Variable | Default | Purpose |
|---|---|---|
| `CONSUL_ENABLED` | `false` | Enable Consul registration |
| `CONSUL_HOST` | `127.0.0.1` | Consul agent host |
| `CONSUL_PORT` | `8500` | Consul agent port |
| `CONSUL_TOKEN` | — | Consul ACL token |
| `SERVICE_ADDRESS` | `127.0.0.1` | Address advertised to Consul |
| `FC_HEALTH_PORT` | `8081` | fc-agent health port |
| `WASM_HEALTH_PORT` | `8082` | wasm-agent health port |
| `GUI_HEALTH_PORT` | `8083` | gui-agent health port |

### Auto-scaler

| Variable | Default | Purpose |
|---|---|---|
| `SCALER_ENABLED` | `false` | Enable background scaler |
| `SCALER_MIN_NODES` | `1` | Minimum Nomad job count |
| `SCALER_MAX_NODES` | `10` | Maximum Nomad job count |
| `SCALER_UP_THRESHOLD` | `0.7` | Pool utilization → scale up |
| `SCALER_DOWN_THRESHOLD` | `0.3` | Pool utilization → scale down |
| `SCALER_INTERVAL` | `60` | Seconds between ticks |
| `NOMAD_ADDR` | `http://127.0.0.1:4646` | Nomad server address |
| `NOMAD_TOKEN` | — | Nomad ACL token |

### Packages

| Variable | Default | Purpose |
|---|---|---|
| `PACKAGES_LOCAL_DIR` | `/tmp/platform-packages` | Local wheel cache (dev fallback) |

### mTLS

| Variable | Default | Purpose |
|---|---|---|
| `MTLS_ENABLED` | `false` | Enable mTLS enforcement |
| `MTLS_CERT_FILE` | `/etc/sandbox/certs/server.crt` | Server certificate |
| `MTLS_KEY_FILE` | `/etc/sandbox/certs/server.key` | Server private key |
| `MTLS_CA_FILE` | `/etc/sandbox/certs/ca.crt` | CA for client cert verification |

---

## Stop and clean up

```bash
make stop    # stop all processes and Docker Compose
make clean   # remove __pycache__, *.egg-info, build artifacts
```

---

## Related documents

- [../product/getting-started.md](../product/getting-started.md)
- [../reference/api-spec.md](../reference/api-spec.md)
- [./troubleshooting.md](./troubleshooting.md)
- [./deploy.md](./deploy.md)
- [../reference/runtime-reference.md](../reference/runtime-reference.md)
