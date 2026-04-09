# platform-docs

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, reviewers, operators |
| Scope | Repository overview and documentation entry points |
| Last updated | April 10, 2026 |

Documentation workspace and local sandbox for a Nomad-based runtime platform with three execution tiers: WASM, Firecracker, and GUI automation. The platform is implemented in Python 3.12+ (FastAPI).

## Overview

This repository serves two purposes:

- it defines the current documentation set for the platform runtime and tool model
- it provides a local sandbox for validating API flow, runtime routing, and agent execution

The current platform model keeps business logic in the control plane and uses Nomad for workload placement. Execution is split across specialized runtime paths for fast stateless work, secure untrusted compute, and browser automation.

## Architecture at a glance

| Layer | Responsibility |
|---|---|
| Control plane | Session lifecycle, runtime routing, policy, tool selection, artifact coordination |
| Nomad | Placement, resource scheduling, lifecycle orchestration |
| WASM runtime | Fast path for small stateless tools |
| Firecracker runtime | Secure compute path for untrusted code and heavier execution |
| GUI runtime | Browser and interaction-heavy automation |
| Shared services | PostgreSQL, Redis, MinIO, Consul, HAProxy |

## Repository map

| Path | Purpose |
|---|---|
| `docs/` | Reader-facing documentation: overview, architecture, how-to guides, references, operations |
| `sandbox-worker/` | Platform implementation: API server, agents, runtime modules, and tests |
| `sandbox-tools/` | Tool definitions by category (python_run, bash_run, browser, office, etc.) |
| `services/` | Infrastructure configuration grouped by `controller/`, `data/`, and `monitoring/` |
| `docker/` | Dockerfiles for sandbox-base, fc-agent, and gui-agent images |
| `tools/` | Operator tooling: Firecracker snapshot builder |
| `examples/` | End-to-end examples: Nomad-based Python runtime sandbox smoke test |
| `ccu/` | Control-plane utilities: Nomad horizontal scaler |

## Source structure

```
sandbox-worker/
  src/
    api/              # FastAPI app, routes, middleware, schemas
    orchestrator/     # Lifecycle, snapshot, hibernation, workspace
    service/          # Business logic: execution, session, artifact, package, streaming
    runtime/          # Runtime drivers: firecracker.py, wasm.py, gui.py
    adapters/         # External integrations: registry (Consul), storage (MinIO/local)
    communication/    # Guest agent comms: vsock, stream
    models/           # Pydantic models: session, vm, job, workspace, tenant
    config/           # settings.py
  tests/
    unit/
    integration/
  dashboard/          # Sandbox dashboard UI
  pyproject.toml      # Entry points: platform-api, fc-agent, wasm-agent, gui-agent
```

## Documentation map

Start with these documents:

1. [docs/README.md](./docs/README.md)
2. [docs/overview/platform-overview.md](./docs/overview/platform-overview.md)
3. [docs/architecture/system-overview.md](./docs/architecture/system-overview.md)
4. [docs/reference/runtime-reference.md](./docs/reference/runtime-reference.md)
5. [docs/reference/api-spec.md](./docs/reference/api-spec.md)
6. [docs/how-to/deploy.md](./docs/how-to/deploy.md)
7. [docs/operations/roadmap.md](./docs/operations/roadmap.md)

Use [docs/archive/legacy-kubernetes-reference.md](./docs/archive/legacy-kubernetes-reference.md) only for migration history and design background.

## How to start

For detailed setup and validation instructions, use [docs/how-to/run-locally.md](./docs/how-to/run-locally.md).

Quick start (from repo root):

```bash
# 1. Install worker deps
make worker-install

# 2. Start backing services (Consul, MinIO, Postgres, Redis)
make services-up

# 3. Deploy to local Nomad cluster
make deploy
```

The API is expected on `http://localhost:8080`. Agents run on ports 8081 (fc), 8082 (wasm), 8083 (gui).

To run the worker directly without Nomad:

```bash
cd sandbox-worker
make dev
```

To check agent health:

```bash
make health
```

To stop:

```bash
make services-down
```

## Sandbox components

| Component | Entry point | Role |
|---|---|---|
| `platform-api` | `api.app:main` | API server: health, sessions, execution routing |
| `fc-agent` | `agents.fc_agent:main` | Firecracker runtime worker |
| `wasm-agent` | `agents.wasm_agent:main` | WASM runtime worker |
| `gui-agent` | `agents.gui_agent:main` | GUI and browser runtime worker |
| `services/` | docker-compose | Layered infra config under `controller/`, `data/`, and `monitoring/` |
| `dashboard/` | — | Sandbox dashboard UI |

## Repository conventions

- Keep reader-facing documents in `docs/`.
- Put reader-facing logs, rollout notes, or progress documents under `docs/`, not in the root README.
- All platform source code lives under `sandbox-worker/src/`.
- Treat `sandbox-worker/.venv/` and `*.egg-info/` as rebuildable output.

## Cluster and infrastructure targets

The root `Makefile` covers the full operator workflow:

```
make cluster-setup       # Setup Nomad + Consul + Firecracker on nodes
make cluster-start       # Start Nomad cluster
make snapshot-build      # Build rootfs → Firecracker snapshot → upload to MinIO
make image-build         # Build Docker images (base, fc-agent, gui-agent)
make image-push          # Push images to registry
make deploy              # Deploy sandbox-worker Nomad job
make worker-test         # Run pytest (unit tests)
make worker-lint         # Run ruff + mypy
```

Use cluster and snapshot targets only on machines prepared for cluster setup, not on a standard workstation.
