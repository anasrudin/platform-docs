# Active Context

> Last updated: 2026-03-11 — Week 1 complete (Day 1–7)

## Current Focus

**Week 2 — Control Plane**

Week 1 complete. Next: API gateway auth + rate limiting, tool registry, Prometheus monitoring.

## Current Blockers

None. Week 1 code complete and tests pass. Real FC/WASM execution requires Linux+KVM/wasmtime.

## Active Development Areas

| Area | Status | Owner |
|---|---|---|
| Architecture docs | ✅ Complete | Claude Code |
| Local sandbox (API + agents) | ✅ Running | Claude Code |
| Day 1-2 infra scripts | ✅ Complete | Claude Code |
| Day 3 Firecracker setup + test | ✅ Complete | Claude Code |
| Day 4 Snapshot Builder | ✅ Complete | Claude Code |
| Day 5 fc-agent real execution | ✅ Complete | Claude Code |
| Day 6 WASM real execution | ✅ Complete | Claude Code |
| Day 7 Artifacts + Week 1 validation | ✅ Complete | Claude Code |

## Supporting Examples

- `examples/python-runtime-sandbox/` now provides the Nomad equivalent of the older kind-oriented Python sandbox smoke test.
- `run-test-nomad.sh` starts local dependencies only when needed, prepares Firecracker snapshot assets, schedules `fc-agent` on Nomad, executes `python_run`, and cleans up what it started.
- `sandbox-python.nomad.hcl.tpl` is the sample Nomad job manifest that replaces the previously referenced Kubernetes YAML shape for this repo.
- `run-test-nomad.sh` was executed successfully on 2026-03-11 in `FC_MODE=sim`, validating the Nomad job flow, API request path, and example cleanup behavior.
- The current validated path for this example is Nomad + `firecracker-sim`; real Firecracker execution for the same example still depends on Linux + `/dev/kvm` + Firecracker assets.

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

## Day 4 Deliverables (✅ Done)

- `tools/snapshot-builder/snapshot-builder.sh` — orchestrator (config → rootfs → snapshot → upload)
- `tools/snapshot-builder/build-rootfs.sh` — Python ext4 rootfs via Docker, embeds guest agent
- `tools/snapshot-builder/upload-minio.sh` — upload artifacts to MinIO platform-snapshots bucket
- `tools/snapshot-builder/config/python-v1.env` — snapshot config (python-v1, 512MiB, 2vCPU)
- `tools/snapshot-builder/test/test-snapshot-builder.sh` — 26/26 tests pass

## Day 5 Deliverables (✅ Done)

- `runtime/firecracker/runtime.go` — real runtime, auto-detect `/dev/kvm`, sim fallback
- `runtime/firecracker/pool.go` — VMPool: warm N VMs, single-use, background replenish
- `runtime/firecracker/vm.go` — VM lifecycle: start FC → restore snapshot → resume → execute
- `runtime/firecracker/snapshot.go` — SnapshotStore: download from MinIO (mc/HTTP) + cache
- `runtime/firecracker/guest.go` — GuestClient: vsock (prod) or TCP (dev)
- `runtime/firecracker/vsock_linux.go` + `vsock_stub.go` — build-tag platform split
- `sandbox-platform/scripts/test-fc-pipeline.sh` — --unit/--sim/--real modes, 9/9 pass

## Day 6 Deliverables (✅ Done)

- `runtime/wasm/runtime.go` — real runtime, auto-detect wasmtime, sim fallback; JSON on stdin
- `runtime/wasm/module_store.go` — ModuleStore: download `{tool}.wasm` from MinIO (mc/HTTP) + cache

## Day 7 Deliverables (✅ Done)

- `internal/artifacts/store.go` — ArtifactStore: Upload/Download via mc + HTTP fallback, EnsureBucket
- `pkg/types/types.go` — ArtifactMeta + ArtifactUploadResponse types
- `cmd/platform-api/main.go` — POST /artifacts (multipart) + GET /artifacts/{key}
- `scripts/test-wasm-pipeline.sh` — --unit/--sim/--real modes, 7/7 unit tests pass

## Next Tasks

1. **Week 2** — API gateway auth + rate limiting
2. **Week 2** — Tool registry discovery API
3. **Week 2** — Prometheus + Grafana monitoring
