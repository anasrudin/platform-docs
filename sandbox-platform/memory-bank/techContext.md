# Tech Context

> Updated: 2026-04-07 — Migrasi Go → Python

## Languages & Frameworks

| Component | Technology | Version |
|---|---|---|
| Control Plane | **Python** | **3.12+** |
| HTTP Framework | **FastAPI** + uvicorn | latest |
| Scheduler | HashiCorp Nomad | latest |
| WASM Runtime | Wasmtime CLI | 22 |
| Secure Compute | Firecracker | 1.8 |
| GUI Runtime | Chromium + Playwright | 126 / 1.45 |
| Database | PostgreSQL + psycopg2 | 16 / 2.9 |
| Cache / Queue | Redis (redis-py) | 7 / 5.x |
| Object Storage | MinIO (minio SDK) | AGPL |
| Data Validation | Pydantic v2 | 2.10 |
| Logging | structlog (JSON) | 24.x |
| Metrics | Prometheus + Grafana | latest |
| Tracing | OpenTelemetry Python | latest |

## Python Dependencies (pyproject.toml)

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "redis>=5.2.0",
    "psycopg2-binary>=2.9.0",
    "minio>=7.2.0",
    "python-multipart>=0.0.12",
    "structlog>=24.4.0",
    "pydantic>=2.10.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "pytest-cov>=5.0.0",
]
```

## Go → Python Dependency Mapping

| Go | Python |
|----|--------|
| `github.com/google/uuid` | `import uuid` (stdlib) |
| `github.com/lib/pq` | `psycopg2-binary` |
| `github.com/redis/go-redis/v9` | `redis` |
| `net/http` server | `fastapi` + `uvicorn` |
| `log/slog` (JSON) | `structlog` |
| `encoding/json` | `json` (stdlib) |
| `os/exec` | `subprocess` |
| `sync.RWMutex` | `threading.RLock` |
| `context.Context` | function param / `asyncio` |
| `go build ./...` | `pip install -e .` |
| `go test ./...` | `pytest` |

## Infrastructure

| Resource | Spec | Role |
|---|---|---|
| node1 | e2-standard-8 (8 vCPU, 32GB) | Control plane + DB + Redis + MinIO |
| node2 | e2-standard-8 | Runtime (WASM + Firecracker) |
| node3 | e2-standard-8 | Runtime (Firecracker + GUI) |

Cloud: **Google Cloud**

## Database Schema (Core Tables)

- `tenants` — identity & quota config
- `sessions` — lifecycle state machine
- `executions` — per-execution record
- `templates` — runtime template metadata
- `policies` — per-tenant policy
- `billing_events` — resource usage tracking
- `audit_log` — append-only audit trail

## Network

- Per-sandbox TAP device → Linux bridge → iptables + tc
- Platform DNS resolver for domain allowlisting
- Default: WASM=offline, FC=restricted, GUI=public/restricted

## Filesystem

- Overlay FS: read-only base + per-sandbox writable layer
- Mount options: `nodev`, `nosuid`, `noexec` (for /tmp)
- Base images stored in MinIO, cached locally on nodes

## Security Stack

| Layer | Mechanism |
|---|---|
| 1 — Runtime | WASM capabilities / Firecracker minimal VM |
| 2 — VM | KVM + Firecracker jailer |
| 3 — Filesystem | Overlay FS (read-only base) |
| 4 — Network | iptables + tc + DNS filtering |
| 5 — Host | seccomp + cgroups + namespaces |
