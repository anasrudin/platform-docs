# Active Context

> Last updated: 2026-03-11 — Day 3 infra complete

## Current Focus

**Week 1 — Runtime Foundation (Day 4 next)**

Day 1-2 (cluster setup) and Day 3 (Firecracker install) are complete.
Next: Day 4 — Snapshot Builder to produce the `python-v1` snapshot used by fc-agent.

## Current Blockers

None. Day 1-3 infra scripts are ready. Day 4 requires a real GCP node with KVM.

## Active Development Areas

| Area | Status | Owner |
|---|---|---|
| Architecture docs | ✅ Complete | Claude Code |
| Local sandbox (API + agents) | ✅ Running | Claude Code |
| Day 1-2 infra scripts | ✅ Complete | Claude Code |
| Day 3 Firecracker setup + test | ✅ Complete | Claude Code |
| Day 4 Snapshot Builder | 🔲 Not started | Platform Team |
| Day 5 fc-agent real execution | 🔲 Not started | Platform Team |
| Day 6 WASM real execution | 🔲 Not started | Platform Team |

## Infra File Map

```
sandbox-platform/infra/
├── docker-compose.yml              ← local dev only
├── nomad/
│   ├── server.hcl                  ← node1 Nomad server
│   └── client.hcl                  ← node2/3 Nomad clients
├── postgres/
│   └── migrations/001_init.sql     ← sessions, jobs, tools schema
├── minio/
│   └── init-buckets.sh             ← creates 3 platform buckets
├── systemd/
│   └── nomad.service               ← systemd unit for Nomad
└── scripts/
    ├── setup-all-nodes.sh          ← install Nomad on all nodes
    ├── setup-control-node.sh       ← install PG + Redis + MinIO on node1
    ├── setup-firecracker.sh        ← install FC binary + KVM + test assets
    ├── verify-day1-2.sh            ← check Day 1-2 goals
    └── test-firecracker.sh         ← check Day 3 goals
```

## Recent Architecture Decisions

1. **Nomad over Kubernetes** — lighter orchestrator, Nomad only does placement
2. **3 separated node pools** — WASM, Firecracker, GUI isolated by `node_class`
3. **Overlay filesystem** — read-only base + per-sandbox writable layer
4. **TAP-based network isolation** — per-sandbox TAP → bridge → iptables
5. **Skill-based tool discovery** — agents find tools by skill, not by name

## Next Tasks

1. **Day 4** — Build `tools/snapshot-builder/` (main.go, builder.go, vm_launcher.go, snapshot_creator.go, artifact_uploader.go)
2. **Day 5** — Replace fc-agent stub with real Firecracker VM pool execution
3. **Day 6** — WASM agent: real Wasmtime execution + MinIO module cache
