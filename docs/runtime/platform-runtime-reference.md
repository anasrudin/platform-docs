# Platform Runtime Reference

This is the condensed runtime view. The authoritative details live in:

- [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md)
- [`memory-bank/architecture-graph.md`](../../memory-bank/architecture-graph.md)
- [`memory-bank/runtime-topology.md`](../../memory-bank/runtime-topology.md)
- [`memory-bank/activeContext.md`](../../memory-bank/activeContext.md)
- [`memory-bank/progress.md`](../../memory-bank/progress.md)
- [`memory-bank/milestone-timeline.md`](../../memory-bank/milestone-timeline.md)

Roadmap is kept separately in [`platform-runtime-roadmap.md`](./platform-runtime-roadmap.md).

## Runtime Model

The platform runs untrusted workloads across three runtime tiers, with all business logic in the control plane and Nomad limited to placement.

| Tier | Engine | Target use | Startup target |
|---|---|---|---|
| WASM | Wasmtime 22 | Fast, stateless tools | `< 5ms` |
| Firecracker | microVM + KVM | Secure compute for untrusted code | `20-80ms` from snapshot |
| GUI | Chromium + Playwright | Browser and visual automation | `~300ms` warm |

## Core Flow

```text
Agent/User
  -> API Gateway
  -> Control Plane
  -> Tool Registry
  -> Nomad
  -> wasm-host-agent / fc-host-agent / gui-host-agent
  -> PostgreSQL + Redis/NATS + MinIO
```

Control-plane responsibilities:

- auth, rate limiting, request logging
- session lifecycle and runtime routing
- policy, quota/billing, audit, cleanup
- tool discovery and health tracking

Non-negotiable design rules:

- Nomad does placement only, not business logic
- runtime pools are isolated by workload profile
- Firecracker sandboxes use overlay filesystems and TAP-based networking
- execution artifacts and records are stored outside the sandbox lifecycle

## Current Topology

The memory bank currently defines a 3-node MVP cluster:

| Node | Role | Notes |
|---|---|---|
| `node1` | Control plane | API Gateway, Control Plane, Tool Registry, PostgreSQL, Redis, MinIO, Nomad server |
| `node2` | WASM + Firecracker runtime | Wasmtime executor, `wasm-host-agent`, `fc-host-agent` |
| `node3` | Firecracker + GUI runtime | `fc-host-agent`, `gui-host-agent`, Chromium/stream server |

MVP still runs as a local minimal sandbox first, with mixed runtime nodes before splitting into dedicated pools at scale.

## Current Implementation State

The current source-of-truth status is:

| Area | Status |
|---|---|
| Architecture docs | complete and compacted |
| API Gateway | minimal local implementation |
| Session Manager | minimal local implementation |
| WASM agent | local minimal implementation |
| Firecracker agent | local stub |
| GUI agent | local stub |
| Tool Registry | not started |
| MinIO integration | not started |
| Network/filesystem isolation | not started |

Local focus from the active context:

- simple API server with routing logic
- PostgreSQL and Redis via docker-compose
- Redis-backed job queues
- local WASM, Firecracker, and GUI agents
- `test-e2e.sh` and Nomad-backed local testing

## Milestones

Near-term milestones from the memory bank:

1. Runtime foundation: Nomad cluster, Firecracker snapshot restore, Wasmtime execution, MinIO artifacts
2. Control plane: auth, rate limit, runtime router, tool registry, monitoring
3. Sandbox execution: GUI runtime, TAP isolation, overlay filesystem, execution recording
4. Agent integration: skill-based selection and full end-to-end execution path

## How To Use This Doc

- Start here for the current architecture snapshot.
- Use the linked memory-bank files for details that need to stay authoritative.
- Treat any older K8s- or 67-tool-era docs as historical unless they were rewritten from the memory bank.
