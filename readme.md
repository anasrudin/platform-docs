# platform-docs

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, reviewers, operators |
| Scope | Repository overview and documentation entry points |
| Last updated | March 11, 2026 |

Documentation workspace and local sandbox for a Nomad-based runtime platform with three execution tiers: WASM, Firecracker, and GUI automation.

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
| Shared services | PostgreSQL, Redis or NATS, MinIO |

## Repository map

| Path | Purpose |
|---|---|
| `docs/` | Reader-facing documentation for overview, architecture, how-to guides, references, operations, and archive material |
| `sandbox-platform/` | Local runnable sandbox: API, agents, infrastructure scripts, and smoke tests |
| `sandbox-tools/` | Tooling and runtime experimentation area |
| `docker/` | Local container support files |
| `scripts/` | Repository utility scripts |
| `memory-bank/` | Internal planning and working context |

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

Quick start:

```bash
cd sandbox-platform
make dev
```

The API is expected on `http://localhost:8080`.

To stop the sandbox:

```bash
cd sandbox-platform
make stop
```

## Current sandbox components

| Component | Role |
|---|---|
| `cmd/platform-api` | API server for health checks, sessions, and execution |
| `cmd/wasm-agent` | WASM runtime worker |
| `cmd/fc-agent` | Firecracker runtime worker |
| `cmd/gui-agent` | GUI and browser runtime worker |
| `infra/` | Node setup, migrations, MinIO bootstrap, and verification scripts |
| `runtime/` | Runtime implementation by execution tier |
| `dashboard/` | Sandbox dashboard UI |

## Repository conventions

- Keep reader-facing documents in `docs/`.
- Put reader-facing logs, rollout notes, or progress documents under `docs/`, not in the root README.
- Treat `memory-bank/` as internal planning material rather than primary repository documentation.
- Treat `sandbox-platform/bin/` as rebuildable output.

## Production-oriented targets

`sandbox-platform/Makefile` includes targets for a more production-like environment:

- `make infra-setup-node`
- `make infra-setup-control`
- `make infra-migrate`
- `make infra-buckets`
- `make infra-verify`
- `make infra-fc-setup`
- `make infra-fc-test`

Use those targets only on machines prepared for cluster setup, not on a standard workstation.
