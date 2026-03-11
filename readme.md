# platform-docs

Technical documentation for **platform-runtime** and **platform-tools**.

This platform is a multi-engine sandbox runtime that executes workloads across 3 different runtime tiers: WASM, Firecracker, and GUI — running on top of HashiCorp Nomad as the scheduler.

---

## Memory Bank

Persistent memory system for multi-agent collaboration. **Every AI agent MUST read all files in `/memory-bank/` before starting work.**

| File | Contents |
|---|---|
| [projectbrief.md](./memory-bank/projectbrief.md) | Mission, architecture, constraints |
| [productContext.md](./memory-bank/productContext.md) | Problem, users, success criteria |
| [systemPatterns.md](./memory-bank/systemPatterns.md) | Architecture patterns, anti-patterns |
| [techContext.md](./memory-bank/techContext.md) | Stack, dependencies, security layers |
| [activeContext.md](./memory-bank/activeContext.md) | Current focus, blockers, next tasks |
| [progress.md](./memory-bank/progress.md) | Platform capabilities status |
| [milestone-timeline.md](./memory-bank/milestone-timeline.md) | Milestone status + validation criteria |
| [architecture-graph.md](./memory-bank/architecture-graph.md) | System diagram + data flows |
| [runtime-topology.md](./memory-bank/runtime-topology.md) | Node specs, services, scaling path |
| [tool-registry.md](./memory-bank/tool-registry.md) | All tools, skills, runtime mapping |
| [decisions.md](./memory-bank/decisions.md) | Architecture decisions log (ADR) |
| [development-log.md](./memory-bank/development-log.md) | Session history |

---

## Current Docs

`memory-bank/` is authoritative. `docs/` now contains a compact view derived from the memory bank instead of parallel long-form copies.

| Document | Description |
|---|---|
| [docs/README.md](./docs/README.md) | Compact doc index and maintenance rules |
| [runtime reference](./docs/runtime/platform-runtime-reference.md) | Current runtime architecture, topology, and MVP status |
| [runtime roadmap](./docs/runtime/platform-runtime-roadmap.md) | Current phased build roadmap tied to the memory bank |
| [tools reference](./docs/tools/platform-tools-reference.md) | Current tool model, registry snapshot, and skill routing |
| [legacy Kubernetes reference](./docs/archive/legacy-kubernetes-reference.md) | Historical K8s/GKE-era context only |

---

## Local Sandbox (`/sandbox-platform`)

Minimal, self-contained local developer environment using standard Go tools without orchestrator overhead.

### Prerequisites

To run the local sandbox, you must have the following installed on your machine:
- **Go** (1.21+) - for building the binaries
- **Docker & Docker Compose** - for running PostgreSQL and Redis
- **Nomad** - for running the `fc-agent` in a simulated orchestrator
  - **macOS:** `brew tap hashicorp/tap && brew install hashicorp/tap/nomad`
  - **Linux (Ubuntu/Debian):**
    ```bash
    wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
    sudo apt update && sudo apt install nomad
    ```
- **jq** & **curl** - for parsing JSON output and making API requests in the E2E test script
  - **macOS:** `brew install jq curl`
  - **Linux (Ubuntu/Debian):** `sudo apt install jq curl`

### Commands

Navigate to `/sandbox-platform` and use the following commands:

#### Local Dev

- `make build` : Build all binaries (`platform-api`, `wasm-agent`, `fc-agent`, `gui-agent`)
- `make dev` : Run the infrastructure (PostgreSQL + Redis + MinIO) via docker-compose, wait until healthy, then run all binaries locally.
- `make dev-nomad` : Same as `make dev`, but starts a local **Nomad dev agent** and deploys `fc-agent` as a Nomad job instead of running it bare-metal.
- `make run` : Run the API service & Agents locally.
- `make stop` : Stop the local services, Nomad jobs, and backend infrastructure.
- `make clean` : Clean build files in the `bin/` directory.

#### Production Infrastructure (GCP Nodes)

Run these on the actual GCP cluster nodes. All scripts are in `infra/`.

**Day 1–2 — Cluster Setup (run on each node, then node1 only):**

| Command | Run on | What it does |
|---|---|---|
| `make infra-setup-node` | all 3 nodes | Install Nomad + base deps |
| `make infra-setup-control` | node1 only | Install PostgreSQL 16 + Redis 7 + MinIO |
| `make infra-migrate` | node1 only | Apply DB schema migrations |
| `make infra-buckets` | node1 only | Create MinIO buckets |
| `make infra-verify` | node1 | Verify all Day 1-2 goals pass |

**Day 3 — Firecracker (run on node2 and node3):**

| Command | Run on | What it does |
|---|---|---|
| `make infra-fc-setup` | node2, node3 | Install Firecracker binary + enable KVM + download test assets |
| `make infra-fc-test` | node2, node3 | Verify: `firecracker --version`, `/dev/kvm`, microVM boot |

### Local Components

1. **`platform-api`** : API Server (`:8080`) for `GET /health`, `POST /sessions` and `POST /execute`. Connects to Postgres & Redis.
2. **`wasm-agent`** : Local job consumer for the WASM queue. Executes mock modules that return realistic responses.
3. **`fc-agent`** : Local job consumer for the MicroVM (Firecracker) queue. Currently uses a mock execution stub with artificial delay.
4. **`gui-agent`** : Local job consumer for the GUI Runtime (Chromium). Currently uses a mock stub.

### Testing & Dashboard

- **End-to-End Test**: After starting the sandbox (with `make dev` or `make dev-nomad`), run `./test-e2e.sh` from the `/sandbox-platform` folder. This script automatically tests the API, session creation, and simulates execution of tools across WASM, Firecracker, and GUI queues.
- **Nomad Dashboard**: When running `make dev-nomad`, a local Nomad UI is started. You can monitor jobs, resource allocations, and agent health at **[http://localhost:4646](http://localhost:4646)**.

---

## Brief Architecture

```
[Agent / User]
    │
    ▼
[API Gateway]          ← auth, rate limit, tenant routing
    │
    ▼
[Control Plane]        ← session, routing, policy, billing, janitor, audit
    │
    ├── [Tool Registry] ← tool discovery, skill mapping, health tracking
    │
    ▼
[Nomad Scheduler]      ← placement, resource packing, lifecycle
    │
    ├── [WASM Pool]         wasm-host-agent + Wasmtime
    ├── [Firecracker Pool]  fc-host-agent + FC + warm VM pool + overlay fs + TAP network
    └── [GUI Pool]          gui-host-agent + Chromium + stream server

[Shared Infra]
    ├── PostgreSQL
    ├── Redis / NATS
    └── MinIO
```

## Runtime Tiers

| Tier | Runtime | Cold Start | Use Case |
|---|---|---|---|
| **WASM** | Wasmtime 22 | < 5ms | Fast, stateless tools |
| **Firecracker** | microVM + KVM | 20–80ms (snapshot) | Secure, untrusted code |
| **GUI** | Chromium + Playwright | ~300ms (warm) | Browser automation |

## Security Layers

| Layer | Mechanism |
|---|---|
| 1 — Runtime | WASM capability sandbox / Firecracker minimal VM |
| 2 — VM | KVM hypervisor + Firecracker jailer |
| 3 — Filesystem | Read-only base image + overlay writable layer |
| 4 — Network | iptables allowlist + tc rate limit + DNS filtering |
| 5 — Host | seccomp + cgroups + namespaces |
