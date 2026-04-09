# Release Notes

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, operators, integrators |
| Scope | Changelog for all platform releases |
| Last updated | April 8, 2026 |

---

## v0.2.0 — April 8, 2026

### Summary

Full Python migration complete. Five advanced feature phases shipped. All 235 tests passing at ≥ 95% coverage on new code.

### Breaking changes

- **Runtime language**: The platform codebase migrated from Go 1.25 to Python 3.12+. All Go binaries have been removed.
- **Entry point names**: The `cmd/` package was renamed to `platform_cmd/` to avoid conflict with the Python standard library `cmd` module. Entry point commands remain the same (`platform-api`, `fc-agent`, `wasm-agent`, `gui-agent`).
- **Install method**: `go build` is replaced by `pip install -e ".[dev]"`. See [../how-to/run-locally.md](../how-to/run-locally.md).
- **Artifact download path**: `GET /artifacts/{key}` (flat key) is replaced by `GET /artifacts/{artifact_id}/{name}`.

### New features

#### Phase 1 — Consul service discovery and health checks

- All three runtime agents (`fc-agent`, `wasm-agent`, `gui-agent`) register with Consul on startup and deregister on graceful shutdown.
- Each agent exposes `GET /health` returning `{"status": "ok", "runtime": "<name>", "pool_size": N}`.
- Consul registration is gated by `CONSUL_ENABLED=true` (default: off).
- Port assignments: fc-agent `:8081`, wasm-agent `:8082`, gui-agent `:8083`.
- New module: `sandbox_platform/consul/client.py` — async Consul client (register, deregister, KV CRUD).
- New module: `sandbox_platform/consul/health_server.py` — lightweight health HTTP server running in a daemon thread.
- +22 unit tests.

#### Phase 2 — HAProxy load balancing and session KV

- HAProxy configuration template (`infra/haproxy/haproxy.cfg.j2`) renders backends from Consul service catalog.
- Dynamic reload via `infra/haproxy/haproxy.cfg.ctmpl` and `infra/haproxy/consul-template.hcl` — zero downtime on backend changes.
- Session-to-VM mappings stored in Consul KV at `sandbox/sessions/{session_id}`.
- New module: `sandbox_platform/session/consul_store.py` — async session store backed by Consul KV.
- +11 unit tests.

#### Phase 3 — Auto-scaling

- Background asyncio task watches pool utilization and calls the Nomad scaling API.
- Configurable policy: `min_nodes`, `max_nodes`, `scale_up_threshold` (default 0.7), `scale_down_threshold` (default 0.3), cooldown periods.
- Scale-down triggers Nomad's migrate-stanza drain — in-flight connections complete before allocation count is reduced.
- Gated by `SCALER_ENABLED=true` (default: off).
- New modules: `sandbox_platform/scaler/metrics.py`, `policy.py`, `nomad.py`, `scaler.py`.
- +41 unit tests.

#### Phase 4 — Package management, TAP naming, MAC generation

- `POST /packages/install` — downloads a pip wheel, caches it in MinIO (`platform-packages/` bucket), and returns metadata. Falls back to local directory when `PACKAGES_LOCAL_DIR` is set.
- `GET /packages` — lists cached package metadata.
- `DELETE /packages/{name}` — removes a cached package.
- TAP device names encode node and VM identity: `tap-{node_short}-{vm_short}` (within Linux 15-char IFNAMSIZ limit).
- MAC addresses are deterministically generated from node ID and VM ID using SHA-256, locally administered unicast format (`06:00:xx:xx:xx:xx`).
- New module: `sandbox_platform/packages/store.py`.
- +35 unit tests.

#### Phase 5 — Mutual TLS (mTLS)

- `create_mtls_context()` builds a server `ssl.SSLContext` with TLS 1.3 minimum and `ssl.CERT_REQUIRED`.
- `CertManager.reload()` hot-swaps the certificate chain on the live `SSLContext` without interrupting existing connections.
- `MTLSMiddleware` returns HTTP 403 when `MTLS_ENABLED=true` and the client certificate is absent.
- Certs resolved from `/etc/sandbox/certs/` by default; configurable via `MTLS_CERT_FILE`, `MTLS_KEY_FILE`, `MTLS_CA_FILE`.
- Gated by `MTLS_ENABLED=true` (default: off).
- New module: `sandbox_platform/security/mtls.py`.
- +22 unit tests.

### Infrastructure changes

- `infra/haproxy/` — HAProxy Jinja2 template, consul-template config, zero-downtime reload HCL.
- `infra/nomad/jobs/` — Nomad job definitions updated for Python agents.
- New MinIO bucket: `platform-packages` for wheel caching.

### New environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONSUL_ENABLED` | false | Enable Consul registration + session KV |
| `CONSUL_HOST` | 127.0.0.1 | Consul agent host |
| `CONSUL_PORT` | 8500 | Consul agent port |
| `CONSUL_TOKEN` | — | Consul ACL token |
| `FC_HEALTH_PORT` | 8081 | fc-agent health port |
| `WASM_HEALTH_PORT` | 8082 | wasm-agent health port |
| `GUI_HEALTH_PORT` | 8083 | gui-agent health port |
| `SERVICE_ADDRESS` | 127.0.0.1 | Address advertised to Consul |
| `SCALER_ENABLED` | false | Enable background auto-scaler |
| `SCALER_MIN_NODES` | 1 | Minimum Nomad job count |
| `SCALER_MAX_NODES` | 10 | Maximum Nomad job count |
| `SCALER_UP_THRESHOLD` | 0.7 | Pool utilization → scale up |
| `SCALER_DOWN_THRESHOLD` | 0.3 | Pool utilization → scale down |
| `SCALER_INTERVAL` | 60 | Seconds between scaler ticks |
| `NOMAD_ADDR` | http://127.0.0.1:4646 | Nomad server address |
| `NOMAD_TOKEN` | — | Nomad ACL token |
| `PACKAGES_LOCAL_DIR` | /tmp/platform-packages | Package wheel cache (local fallback) |
| `MTLS_ENABLED` | false | Enable mTLS enforcement |
| `MTLS_CERT_FILE` | /etc/sandbox/certs/server.crt | Server certificate |
| `MTLS_KEY_FILE` | /etc/sandbox/certs/server.key | Server private key |
| `MTLS_CA_FILE` | /etc/sandbox/certs/ca.crt | CA for client cert verification |

### Known limitations in this release

- Auto-scaler node list is wired to `[]` in `platform_api.py`. Consul-based dynamic node discovery is not yet connected; scaler evaluates policy against empty metrics.
- Package install (`POST /packages/install`) downloads and caches wheels on the host. Execution inside a Firecracker VM session via the guest agent is not yet implemented.
- `proxy_url` in the package install request is passed as `--index-url` instead of `--proxy` — a bug that affects corporate proxy environments.
- mTLS outbound calls (agent → Consul, scaler → Nomad) are plain HTTP. Only inbound requests to `platform-api` are covered by `MTLSMiddleware`.
- `PUT /packages/{name}` (update) and `GET /packages/{name}` (single package info) endpoints are not yet implemented.

---

## v0.1.0 — April 6, 2026

### Summary

Initial Python migration from Go 1.25. Full parity with the Week 1 Go implementation. 91 tests passing.

### What was migrated

| Component | Module |
|---|---|
| Types and domain models | `sandbox_platform/types.py` |
| Redis queue client | `sandbox_platform/queue/client.py` |
| PostgreSQL session manager | `sandbox_platform/session/manager.py` |
| Runtime router | `sandbox_platform/router/router.py` + `rules.py` |
| MinIO artifact store | `sandbox_platform/artifacts/store.py` |
| Firecracker runtime (sim + real) | `sandbox_platform/runtime/firecracker/` |
| WASM runtime | `sandbox_platform/runtime/wasm/` |
| GUI runtime (stub) | `sandbox_platform/runtime/gui/runtime.py` |
| FastAPI entry point | `platform_cmd/platform_api.py` |
| Agent entry points | `platform_cmd/fc_agent.py`, `wasm_agent.py`, `gui_agent.py` |

### Notes

- Firecracker falls back to simulation mode automatically when `/dev/kvm` is absent or `FC_MODE=sim`.
- WASM falls back when Wasmtime CLI is not installed or the MinIO module bucket is absent.
- GUI stub returns a fixed mock response in all environments.
- Project layout uses `src/` with `pyproject.toml` `where = ["src"]`.

---

## v0.0.1 — April 5, 2026 (archived)

Week 1 Go implementation. All Go source files have been removed as part of the v0.1.0 migration. See [../how-to/migrate-go-to-python.md](../how-to/migrate-go-to-python.md) for the migration record.
