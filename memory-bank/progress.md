# Progress

> Last updated: 2026-03-11 — Day 1-2 + Day 3 infra implemented

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
| WASM runtime (Wasmtime) | 🚧 Local stub — Day 6 target |
| Firecracker runtime | 🚧 Local stub — test-firecracker.sh ready for Day 3 verification |
| GUI runtime (Chromium) | 🚧 Local stub — Day 15 target |
| Snapshot builder | 🔲 Day 4 target |
| Warm pool manager | 🔲 Day 13 target |

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
- Stubbed WASM, FC, GUI agents via Redis queue
- E2E test script (`test-e2e.sh`)
- **[Day 1-2]** Production Nomad cluster configs (`infra/nomad/server.hcl`, `client.hcl`)
- **[Day 1-2]** Node setup scripts (`setup-all-nodes.sh`, `setup-control-node.sh`)
- **[Day 1-2]** PostgreSQL schema migrations (`infra/postgres/migrations/001_init.sql`)
- **[Day 1-2]** MinIO bucket init script (`infra/minio/init-buckets.sh`)
- **[Day 1-2]** Nomad systemd service unit + Day 1-2 verification script
- **[Day 3]** Firecracker + KVM setup script (`setup-firecracker.sh`)
- **[Day 3]** Firecracker 3-goal test script (`test-firecracker.sh`) — verifies version, /dev/kvm, VM boot

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

- **Day 4** — Snapshot Builder: boot Firecracker VM, run bootstrap script, create snapshot, upload to MinIO
- **Day 5** — fc-agent with real VM pool (replace stub with actual Firecracker execution)
- **Day 6** — WASM agent with real Wasmtime execution + MinIO module cache
