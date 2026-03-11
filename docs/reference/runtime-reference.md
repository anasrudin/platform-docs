# Platform Runtime Reference

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, reviewers, operators |
| Scope | Current runtime architecture, topology, and implementation maturity |
| Last updated | March 11, 2026 |

## Executive summary

The platform executes untrusted workloads across three runtime tiers: WASM, Firecracker, and GUI automation. The control plane owns business logic, policy, routing, and artifact handling. Nomad is used for placement and lifecycle orchestration, not for application-specific orchestration logic.

Week 1 runtime foundation is complete. WASM and Firecracker now have real implementations, each with capability-aware fallback behavior for constrained development environments. The GUI path remains stubbed while Week 2 moves into control-plane work and Week 3 targets isolation and browser-runtime maturity.

## System boundaries

### In scope

- session lifecycle and runtime routing
- runtime-specific execution workers
- artifact and snapshot storage coordination
- shared infrastructure for metadata, queues, and object storage
- local and cluster-oriented validation paths

### Out of scope today

- full billing and quota enforcement
- multi-region deployment
- complete production security hardening
- autoscaling by dedicated runtime pool

## Runtime architecture

| Tier | Engine | Primary use case | Startup target |
|---|---|---|---|
| WASM | Wasmtime 22 | Fast, stateless tool execution | `< 5ms` |
| Firecracker | microVM + KVM | Secure compute for untrusted code | `20-80ms` from snapshot |
| GUI | Chromium + Playwright | Browser and visual automation | `~300ms` warm |

### Architecture principles

- The control plane owns policy and business logic.
- Nomad is a placement layer, not the business workflow engine.
- Runtime pools are separated by workload profile and isolation needs.
- Firecracker sandboxes use disposable filesystem and network boundaries.
- Execution records and artifacts outlive individual sandbox instances.

## Request lifecycle

```text
Agent or user
  -> API gateway
  -> control plane
  -> tool registry
  -> runtime router
  -> Nomad placement
  -> runtime host agent
  -> PostgreSQL + Redis or NATS + MinIO
```

### Control-plane responsibilities

- authentication, rate limiting, and request logging
- session creation and lifecycle management
- runtime selection and queue routing
- tool discovery, health tracking, and policy enforcement
- audit, cleanup, and artifact coordination

## Deployment topology

The current MVP topology assumes a three-node cluster model, while day-to-day iteration continues in a local sandbox first.

| Node | Role | Current responsibilities |
|---|---|---|
| `node1` | Control node | API gateway, control plane, tool registry, PostgreSQL, Redis, MinIO, Nomad server |
| `node2` | Runtime node | WASM execution, `wasm-host-agent`, `fc-host-agent` |
| `node3` | Runtime node | `fc-host-agent`, `gui-host-agent`, Chromium and stream services |

## Implementation maturity

Status as of March 11, 2026:

| Area | Maturity |
|---|---|
| Documentation set | Stable |
| API gateway | Minimal local implementation |
| Session manager | Minimal local implementation |
| WASM runtime | Real implementation with Wasmtime CLI and MinIO-backed module cache |
| Firecracker runtime | Real implementation with snapshot restore, pool management, and guest transport |
| GUI runtime | Stubbed execution path |
| Tool registry | Not started |
| MinIO artifact integration | Basic implementation for snapshots, modules, and artifacts |
| Network and filesystem isolation | Not started |

## Current engineering focus

- API gateway authentication and rate limiting
- tool registry discovery API
- Prometheus and Grafana monitoring
- continued stabilization of the local WASM and Firecracker paths
- preparation for GUI runtime and isolation work in Week 3

## Milestone alignment

The runtime program currently aligns to four major milestones:

1. Runtime foundation: Nomad cluster, Firecracker snapshot restore, Wasmtime execution, MinIO artifacts
2. Control plane: auth, rate limiting, runtime router, tool registry, monitoring
3. Sandbox execution: GUI runtime, TAP isolation, overlay filesystem, execution recording
4. Agent integration: skill-based selection and full end-to-end execution

The delivery view for those milestones is maintained in [../operations/roadmap.md](../operations/roadmap.md).

## Related documents

- [../overview/platform-overview.md](../overview/platform-overview.md)
- [../architecture/system-overview.md](../architecture/system-overview.md)
- [../operations/roadmap.md](../operations/roadmap.md)
- [tools-reference.md](./tools-reference.md)
- [api-spec.md](./api-spec.md)
- [../how-to/run-locally.md](../how-to/run-locally.md)
- [../how-to/deploy.md](../how-to/deploy.md)
- [../archive/legacy-kubernetes-reference.md](../archive/legacy-kubernetes-reference.md)

## Internal source materials

Detailed planning inputs are maintained in internal project files, including `projectbrief`, `architecture-graph`, `runtime-topology`, `activeContext`, `progress`, and `milestone-timeline`.
