# Progress

> Last updated: 2026-04-08

## Week 1 — Go Implementation (✅ Selesai)

| Hari | Status | Deliverable |
|------|--------|-------------|
| 1–2  | ✅ | Nomad cluster + PG + Redis + MinIO infra scripts |
| 3    | ✅ | Firecracker install + KVM setup + test-firecracker.sh |
| 4    | ✅ | `tools/snapshot-builder/` — rootfs + snapshot + MinIO upload |
| 5    | ✅ | Real Firecracker runtime (pool + vsock + snapshot restore) |
| 6    | ✅ | Real WASM runtime (Wasmtime CLI + MinIO module cache) |
| 7    | ✅ | Artifact upload/download (POST /artifacts, GET /artifacts/{key}) |

## Migrasi Go → Python (✅ Selesai — 2026-04-07)

| Komponen | Status |
|----------|--------|
| Panduan migrasi (`docs/migration/go-to-python.md`) | ✅ |
| Setup Python project (`pyproject.toml`, venv, src/ layout) | ✅ |
| `sandbox_platform/types.py` | ✅ |
| `sandbox_platform/queue/client.py` | ✅ |
| `sandbox_platform/session/manager.py` (PostgreSQL) | ✅ |
| `sandbox_platform/router/` | ✅ |
| `sandbox_platform/artifacts/store.py` (MinIO + local fallback) | ✅ |
| `sandbox_platform/runtime/firecracker/` (sim + real mode) | ✅ |
| `sandbox_platform/runtime/wasm/` | ✅ |
| `sandbox_platform/runtime/gui/` | ✅ |
| `platform_cmd/platform_api.py` (FastAPI) | ✅ |
| `platform_cmd/fc_agent.py` / `wasm_agent.py` / `gui_agent.py` | ✅ |
| Hapus file Go | ✅ |
| 91 pytest passing | ✅ |

## Fitur Lanjutan — Advanced Features (✅ Semua Selesai — 2026-04-08)

| Phase | Fitur | Status | Tests |
|-------|-------|--------|-------|
| 1 | Consul service discovery + health checks | ✅ | +22 |
| 2 | HAProxy load balancing + Session KV (Consul) | ✅ | +11 |
| 3 | Auto-scaling (metrics + policy + Nomad + background task) | ✅ | +41 |
| 4 | Package management API + TAP naming + MAC generation | ✅ | +35 |
| 5 | mTLS (TLS 1.3, ECDSA P-256, cert rotation) | ✅ | +22 |

**Total tests: 235 / 235 passing**

### New Modules Added

```
src/sandbox_platform/
  consul/
    client.py          — ConsulClient (async httpx): register, deregister, KV CRUD
    health_server.py   — make_health_app() + start_health_server() daemon thread
  packages/
    store.py           — PackageStore: pip download → MinIO cache (local fallback)
  scaler/
    metrics.py         — NodeMetrics, AggregateMetrics, MetricsCollector
    policy.py          — ScalingPolicy + evaluate() → ScaleAction (pure function)
    nomad.py           — NomadClient: job_count(), scale_job() (async httpx)
    scaler.py          — Scaler: run()/stop()/_tick() background asyncio task
  security/
    mtls.py            — create_mtls_context(), CertManager.reload(), MTLSMiddleware
  session/
    consul_store.py    — SessionStore: put/get/delete on Consul KV
infra/haproxy/
  haproxy.cfg.j2      — Jinja2 template (static deploy-time render)
  haproxy.cfg.ctmpl   — Go template for consul-template dynamic reload
  consul-template.hcl — consul-template config with zero-downtime HAProxy reload
```

### Coverage — New Code

| Module | Coverage |
|--------|----------|
| consul/client.py | 100% |
| consul/health_server.py | 100% |
| packages/store.py | 100% |
| scaler/metrics.py | 96% |
| scaler/nomad.py | 100% |
| scaler/policy.py | 100% |
| scaler/scaler.py | 100% |
| security/mtls.py | 100% |
| session/consul_store.py | 100% |

### Platform API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Platform health (Postgres + Redis) |
| POST | /sessions | Create session |
| POST | /execute | Execute job |
| POST | /artifacts | Upload artifact |
| GET | /artifacts/{id}/{name} | Download artifact |
| POST | /packages/install | Install pip package (cached in MinIO) |
| GET | /packages | List cached packages |
| DELETE | /packages/{name} | Remove package from cache |

### Environment Variables Introduced

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONSUL_ENABLED` | false | Enable Consul registration + session KV |
| `CONSUL_HOST` | 127.0.0.1 | Consul agent host |
| `CONSUL_PORT` | 8500 | Consul agent port |
| `CONSUL_TOKEN` | — | Consul ACL token |
| `FC_HEALTH_PORT` | 8081 | fc-agent /health port |
| `WASM_HEALTH_PORT` | 8082 | wasm-agent /health port |
| `GUI_HEALTH_PORT` | 8083 | gui-agent /health port |
| `SERVICE_ADDRESS` | 127.0.0.1 | Address advertised to Consul |
| `SCALER_ENABLED` | false | Enable background auto-scaler |
| `SCALER_MIN_NODES` | 1 | Minimum Nomad job count |
| `SCALER_MAX_NODES` | 10 | Maximum Nomad job count |
| `SCALER_UP_THRESHOLD` | 0.7 | Pool utilization → scale up |
| `SCALER_DOWN_THRESHOLD` | 0.3 | Pool utilization → scale down |
| `SCALER_INTERVAL` | 60 | Seconds between scaler ticks |
| `NOMAD_ADDR` | http://127.0.0.1:4646 | Nomad server |
| `NOMAD_TOKEN` | — | Nomad ACL token |
| `PACKAGES_LOCAL_DIR` | /tmp/platform-packages | Package wheel cache (local fallback) |
| `MTLS_ENABLED` | false | Enable mTLS enforcement (HTTP 403 without cert) |
| `MTLS_CERT_FILE` | /etc/sandbox/certs/server.crt | Server certificate |
| `MTLS_KEY_FILE` | /etc/sandbox/certs/server.key | Server private key |
| `MTLS_CA_FILE` | /etc/sandbox/certs/ca.crt | CA for client cert verification |

## Infrastructure

| Komponen | Status |
|----------|--------|
| Nomad cluster (3 nodes) | ✅ Scripts tersedia |
| PostgreSQL | ✅ Docker Compose tersedia |
| Redis | ✅ Docker Compose tersedia |
| MinIO | ✅ Docker Compose tersedia |
| HAProxy + consul-template | ✅ Templates + HCL tersedia (`infra/haproxy/`) |

## Yang Bisa Dijalankan Sekarang

```bash
cd sandbox-platform

# Install + test
pip install -e ".[dev]"
pytest                          # 235/235 pass

# Dev environment
make dev                        # start Docker Compose (PG + Redis + MinIO)
make run                        # start platform-api on :8080
make stop / make clean

# With Consul (optional)
CONSUL_ENABLED=true fc-agent
CONSUL_ENABLED=true wasm-agent
CONSUL_ENABLED=true gui-agent

# With auto-scaling (optional)
SCALER_ENABLED=true platform-api

# With mTLS (optional)
MTLS_ENABLED=true platform-api
```
