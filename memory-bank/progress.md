# Progress

> Last updated: 2026-03-11 — Week 1 complete (Day 1–7)

## Platform Capabilities

### Documentation (✅ Complete)

| Document | Status |
|---|---|
| Architecture (28 sections) | ✅ |
| Folder tree + structure | ✅ |
| Coding agent prompt (10 tasks) | ✅ |
| Tools structure + manifest format | ✅ |
| 3-week build roadmap | ✅ |
| Memory Bank system | ✅ |

### Infrastructure

| Component | Status |
|---|---|
| Nomad cluster (3 nodes) | ✅ Local dev (start-nomad-cluster.sh) + production HCL configs (infra/nomad/) |
| PostgreSQL | ✅ Local docker-compose + production setup + migrations (infra/postgres/migrations/001_init.sql) |
| Redis | ✅ Local docker-compose + production setup (setup-control-node.sh) |
| MinIO | ✅ Local docker-compose + production setup + bucket init (infra/minio/init-buckets.sh) |
| Firecracker install | ✅ setup-firecracker.sh (downloads binary, enables KVM, fetches test assets) |
| KVM setup | ✅ kvm_intel/kvm_amd modprobe + /dev/kvm permissions |

### Runtime Engines

| Engine | Status |
|---|---|
| WASM runtime (Wasmtime) | ✅ Real implementation — Wasmtime CLI + MinIO module cache |
| Firecracker runtime | ✅ Real implementation — pool + vsock + snapshot restore |
| GUI runtime (Chromium) | 🚧 Local stub — Day 15 target |
| Snapshot builder | ✅ tools/snapshot-builder/ — python-v1, build+upload pipeline |
| Warm pool manager | ✅ pool.go — in-process VM pool, Day 5 complete |

### Control Plane

| Service | Status |
|---|---|
| API Gateway | 🚧 Local minimal impl |
| Session Manager | 🚧 Local minimal impl |
| Runtime Router | 🚧 Local minimal impl |
| Policy Engine | 🔲 |
| Billing / Quota | 🔲 |
| Janitor / Reaper | 🔲 |
| Audit Service | 🔲 |
| Tool Registry | 🔲 |

### Isolation (🔲 Not Started)

| Feature | Status |
|---|---|
| Network isolation (TAP) | 🔲 |
| Filesystem overlay | 🔲 |
| DNS resolver | 🔲 |
| seccomp profiles | 🔲 |

### Tools (🔲 Not Started)

| Category | Count | Status |
|---|---|---|
| WASM tools | 11 planned | 🔲 |
| Firecracker tools | 10 planned | 🔲 |
| GUI tools | 6 planned | 🔲 |

## What Works Today

- Full architecture documentation + Memory Bank
- Minimal local dev environment (`make dev`, `make dev-nomad`)
- API Server with session + routing logic (PostgreSQL + Redis)
- Redis-backed agent execution path, with real WASM and Firecracker implementations and a stubbed GUI path
- E2E test script (`test-e2e.sh`)
- **[Day 1-2]** Production Nomad cluster configs (`infra/nomad/server.hcl`, `client.hcl`)
- **[Day 1-2]** Node setup scripts (`setup-all-nodes.sh`, `setup-control-node.sh`)
- **[Day 1-2]** PostgreSQL schema migrations (`infra/postgres/migrations/001_init.sql`)
- **[Day 1-2]** MinIO bucket init script (`infra/minio/init-buckets.sh`)
- **[Day 1-2]** Nomad systemd service unit + Day 1-2 verification script
- **[Day 3]** Firecracker + KVM setup script (`setup-firecracker.sh`)
- **[Day 3]** Firecracker 3-goal test script (`test-firecracker.sh`) — verifies version, /dev/kvm, VM boot
- **[Day 4]** `tools/snapshot-builder/` — snapshot-builder.sh, build-rootfs.sh, upload-minio.sh, config/python-v1.env
- **[Day 4]** Guest agent Python embedded in rootfs (`/opt/agent/agent.py`) — vsock/TCP, dispatches python_run/bash_run/echo
- **[Day 4]** Snapshot builder test suite — 26/26 tests pass, no KVM/Docker required
- **[Day 5]** Real Firecracker runtime (`runtime/firecracker/`) — pool, vm, snapshot, guest, vsock
- **[Day 5]** Auto-detect mode: `/dev/kvm` → real, no KVM → sim with graceful fallback
- **[Day 5]** FC pipeline test script (`scripts/test-fc-pipeline.sh`) — 9/9 unit tests pass
- **[Day 6]** Real WASM runtime (`runtime/wasm/runtime.go` + `module_store.go`) — Wasmtime CLI subprocess, sim fallback
- **[Day 6]** `ModuleStore` — MinIO `platform-modules` bucket, local cache `/var/sandbox/wasm-cache/`
- **[Day 6]** Auto-detect: `WASM_MODE` env → wasmtime in PATH → sim fallback
- **[Day 7]** Artifact store (`internal/artifacts/store.go`) — Upload/Download via `mc`, HTTP fallback
- **[Day 7]** `POST /artifacts` + `GET /artifacts/{key}` endpoints in platform-api
- **[Day 7]** `ArtifactUploadResponse` + `ArtifactMeta` types added to `pkg/types/types.go`
- **[Day 7]** WASM pipeline test script (`scripts/test-wasm-pipeline.sh`) — 7/7 unit tests pass
- **[Example]** Nomad Python runtime sample (`examples/python-runtime-sandbox/`) — builds or stubs Firecracker assets, submits `fc-agent` to Nomad, and verifies `python_run`
- **[Example]** `run-test-nomad.sh` verified on 2026-03-11 in `firecracker-sim` mode — successful Nomad deploy, API execution, and cleanup

## Makefile Infra Targets

| Target | Description |
|---|---|
| `make infra-setup-node` | Install Nomad on all nodes |
| `make infra-setup-control` | Install PostgreSQL + Redis + MinIO on node1 |
| `make infra-migrate` | Apply DB migrations |
| `make infra-buckets` | Create MinIO buckets |
| `make infra-verify` | Verify Day 1-2 goals |
| `make infra-fc-setup` | Install Firecracker + KVM (node2/node3) |
| `make infra-fc-test` | Verify Day 3 goals |

## What's Next

- **Week 2** — Control plane: API gateway auth + rate limiting, session manager, tool registry, warm-pool management, Prometheus + Grafana monitoring
