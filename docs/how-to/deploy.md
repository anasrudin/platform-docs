# Deploy the Platform

| Field | Value |
|---|---|
| Status | Active |
| Audience | Operators, contributors |
| Scope | Current cluster bootstrap path for the Nomad-based MVP environment |
| Last updated | March 11, 2026 |

## Executive summary

This guide documents the repository's current deployment path for the MVP environment. At this stage, the deployable scope is infrastructure bootstrap plus runtime prerequisites for a three-node Nomad cluster.

This is not yet a full production application deployment guide for every control-plane service. It is the operational path supported by the current scripts and Make targets in `sandbox-platform/`.

## Target topology

| Node | Role | Expected responsibilities |
|---|---|---|
| `node1` | Control node | Nomad server, PostgreSQL, Redis, MinIO, control-plane support services |
| `node2` | Runtime node | Nomad client, WASM execution, Firecracker execution |
| `node3` | Runtime node | Nomad client, Firecracker execution, GUI execution |

## Prerequisites

- Debian- or Ubuntu-based Linux hosts
- `sudo` access on all nodes
- network connectivity between all three nodes
- KVM support enabled on runtime nodes for Firecracker
- repository contents available on the target hosts

## Deployment phases

### Phase 1: Base setup on all nodes

Run on `node1`, `node2`, and `node3`:

```bash
cd sandbox-platform
make infra-setup-node
```

This installs:

- Nomad
- `curl`
- `jq`
- certificate and package management dependencies

The underlying script is `infra/scripts/setup-all-nodes.sh`.

### Phase 2: Control node bootstrap

Run on `node1`:

```bash
cd sandbox-platform
make infra-setup-control
```

This installs and starts:

- PostgreSQL 16
- Redis 7
- MinIO
- the Nomad server configuration

It also initializes MinIO buckets through `infra/minio/init-buckets.sh`.

### Phase 3: Configure Nomad runtime nodes

On `node2` and `node3`, deploy the Nomad client configuration from:

- `infra/nomad/client.hcl`
- `infra/systemd/nomad.service` if you need the provided unit file

Before starting Nomad clients:

- replace `NODE1_IP` in `client.hcl` with the internal IP of `node1`
- set the node name to `node2` or `node3`
- use port offsets appropriate for each node as documented in the file

Then enable and start Nomad:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nomad
sudo systemctl start nomad
```

### Phase 4: Database migration and bucket verification

Run on `node1` after the control node services are up:

```bash
cd sandbox-platform
NODE1_IP=<node1-ip> make infra-migrate
MINIO_ENDPOINT=http://<node1-ip>:9000 make infra-buckets
NODE1_IP=<node1-ip> make infra-verify
```

This applies:

- `infra/postgres/migrations/001_init.sql`
- MinIO bucket creation and policies
- Day 1-2 verification checks

### Phase 5: Firecracker runtime bootstrap

Run on `node2` and `node3`:

```bash
cd sandbox-platform
make infra-fc-setup
make infra-fc-test
```

This installs:

- Firecracker
- `jailer`
- test kernel and root filesystem assets

It also validates:

- `firecracker --version`
- `/dev/kvm` availability
- manual microVM boot

## Exposed ports

| Service | Port | Node |
|---|---|---|
| Nomad UI and API | `4646` | `node1` |
| Nomad RPC | `4647` | `node1` |
| PostgreSQL | `5432` | `node1` |
| Redis | `6379` | `node1` |
| MinIO API | `9000` | `node1` |
| MinIO Console | `9001` | `node1` |

## Verification checklist

Deployment should be considered successful when all of the following are true:

- the Nomad API is reachable on `node1:4646`
- at least three Nomad nodes are ready
- PostgreSQL is accepting connections and the `platform` database exists
- Redis responds to `PING`
- MinIO health and console endpoints are reachable
- MinIO buckets exist:
  - `platform-artifacts`
  - `platform-tools`
  - `platform-snapshots`
- Firecracker validation passes on `node2` and `node3`

## Current limitations

- application-level deployment for all control-plane services is still evolving
- runtime host agents are not yet fully documented as Nomad jobs for the cluster path
- some runtime paths remain stubbed in the current MVP implementation
- security hardening, billing, and multi-region concerns are outside the current deployment scope

## Related documents

- [run-locally.md](./run-locally.md)
- [../architecture/system-overview.md](../architecture/system-overview.md)
- [../reference/runtime-reference.md](../reference/runtime-reference.md)
- [../operations/roadmap.md](../operations/roadmap.md)
