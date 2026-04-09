---
status: active
audience: contributors
last_updated: 2026-04-09
---

# ADR-002: Migrate to Nomad Worker architecture

- **Status:** Accepted — Implemented
- **Date:** 2026-04-09
- **Deciders:** @anasrudin

## Context and problem statement

The platform architecture evolved through two phases. In Phase 1, the codebase was refactored from a domain-first layout (`sandbox_platform/`, `platform_cmd/`) to a layer-based layout (`api/`, `service/`, `orchestrator/`, `runtime/`, `adapters/`). This completed on 2026-04-09.

After Phase 1, the architecture still used a centralized API + queue-based agent model:

```
client → platform-api (central) → Redis Queue → fc-agent / wasm-agent / gui-agent
```

This model had four problems:
1. The central API is a single point of failure.
2. Workers (agents) have no API of their own — HAProxy cannot health-check them directly.
3. Redis is used as a job queue, adding an unnecessary dependency.
4. Postgres is used in workers for session state, which is not a worker concern.

The `ccu/nomad-horizontal-scaler` reference implementation proved a simpler model works: each Nomad client node runs its own FastAPI + VM pool, and HAProxy load-balances directly to each node.

## Considered options

| Option | Summary |
|--------|---------|
| A | Keep centralized API + Redis queue + agent workers |
| B | Entity-based model: each worker node runs FastAPI + VM pool, registers to Consul, HAProxy routes directly |

## Decision outcome

**Chosen: Option B — Entity-based Nomad Worker model** — eliminates the single point of failure, removes Redis from the worker path, enables direct HAProxy health checks, and simplifies session state to in-memory per node.

### Pros

- No single point of failure — each node is independent
- HAProxy health-checks directly against each worker's `/health` endpoint
- No Redis dependency in the worker execution path
- Session state is in-memory — faster and simpler
- Consul registration on startup — HAProxy backends auto-update via consul-template

### Cons

- Sessions are not shared across nodes — clients require sticky sessions via HAProxy
- No global job history (Postgres is not used in workers)
- Scale-down can lose in-flight sessions

## Consequences

The repository is organized into three entities:

| Entity | Components | Location |
|--------|------------|----------|
| Controller | Consul, HAProxy | `services/consul/`, `services/haproxy/` |
| Worker | Nomad job + FastAPI + VM pool | `sandbox-worker/` |
| Data | MinIO, Postgres | `services/minio/`, `services/postgres/` |

Each worker node (`sandbox-worker/`) owns its execution path end-to-end:

```
POST /execute
  → api/routes/execute.py
  → service/execution.py
      → orchestrator/lifecycle.py  (acquire VM from pool)
      → runtime/firecracker.py     (run job via GuestClient)
      → communication/guest.py     (vsock → VM)
      ← RuntimeResult
  → lifecycle.py                   (release VM back to pool)
  ← response JSON
```

`sandbox-worker/src/` layer structure:

| Layer | Purpose |
|-------|---------|
| `api/` | FastAPI app, middleware, routes, schemas |
| `service/` | Business logic local to each node |
| `orchestrator/` | VM lifecycle, snapshot, hibernation |
| `runtime/` | Firecracker, WASM, GUI execution engines |
| `communication/` | vsock transport, guest client, stream reader |
| `adapters/` | Consul registry, MinIO storage, tracing |
| `models/` | Job, Session data models |
| `config/` | Environment variable settings |

Remaining work before this ADR is fully closed:
- Build and push Docker image to registry
- End-to-end test: deploy to Nomad cluster, verify HAProxy routing and Consul health checks
