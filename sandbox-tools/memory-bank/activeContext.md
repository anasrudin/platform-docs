# Active Context

> Last updated: 2026-03-11 by Antigravity Agent

## Current Focus

**Milestone 1 — Runtime Foundation** (Week 1)

Building the foundational runtime infrastructure:
- Nomad cluster setup (3 nodes)
- Firecracker microVM boot + snapshot builder
- WASM runtime (Wasmtime) + module cache
- Artifact storage (MinIO)

## Current Blockers

None at this time. Architecture documentation is complete. Ready for implementation.

## Active Development Areas

| Area | Status | Owner |
|---|---|---|
| Architecture docs | ✅ Complete | Antigravity Agent |
| Memory Bank setup | ✅ Complete | Antigravity Agent |
| Nomad cluster setup | 🔲 Not started | Platform Team |
| Firecracker runtime | 🔲 Not started | Platform Team |
| WASM runtime | 🔲 Not started | Platform Team |
| API Gateway | 🔲 Not started | Platform Team |
| Tool Registry | 🔲 Not started | Platform Team |

## Recent Architecture Decisions

1. **Nomad over Kubernetes** — lighter orchestrator, Nomad only does placement
2. **3 separated node pools** — WASM, Firecracker, GUI isolated by `node_class`
3. **Overlay filesystem** — read-only base + per-sandbox writable layer
4. **TAP-based network isolation** — per-sandbox TAP → bridge → iptables
5. **Skill-based tool discovery** — agents find tools by skill, not by name

## Next Tasks

1. Setup Nomad cluster (node1=server, node2+node3=client)
2. Install Firecracker on runtime nodes
3. Build snapshot-builder tool
4. Create python-v1 snapshot
5. Deploy fc-host-agent
