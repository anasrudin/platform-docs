# Runtime Topology

> Last updated: 2026-03-11

## Cluster Overview

```
Google Cloud e2-standard-8 (8 vCPU · 32GB RAM)

node1  →  Control Plane
node2  →  Runtime (WASM + Firecracker)
node3  →  Runtime (Firecracker + GUI)
```

## Node 1 — Control Plane

**Nomad role:** Server

**Services:**
| Service | Port | Status |
|---|---|---|
| API Gateway | 8080 | 🔲 |
| Control Plane | 8090 | 🔲 |
| Tool Registry | 8081 | 🔲 |
| PostgreSQL | 5432 | 🔲 |
| Redis | 6379 | 🔲 |
| MinIO | 9000 (API) / 9001 (Console) | 🔲 |
| Nomad Server | 4646 / 4647 / 4648 | 🔲 |
| Prometheus | 9090 | 🔲 |
| Grafana | 3000 | 🔲 |

## Node 2 — Runtime (WASM + Firecracker)

**Nomad role:** Client  
**Node class:** `mixed` (WASM + Firecracker)

**Services:**
| Service | Status |
|---|---|
| wasm-host-agent | 🔲 |
| fc-host-agent | 🔲 |
| Firecracker + jailer | 🔲 |
| Wasmtime | 🔲 |

**Resources:**
| Resource | Capacity |
|---|---|
| WASM concurrent tasks | ~5,000/sec |
| FC warm VMs | 20 (default pool) |
| FC snapshot cache | `/var/lib/platform/snapshots/` |
| WASM module cache | `/var/lib/platform/wasm-modules/` |

**Network:**
| Component | Config |
|---|---|
| Bridge | `bridge0` (172.20.0.0/16) |
| NAT | iptables MASQUERADE |
| DNS | Platform resolver at 172.20.0.1:53 |

## Node 3 — Runtime (Firecracker + GUI)

**Nomad role:** Client  
**Node class:** `mixed` (Firecracker + GUI)

**Services:**
| Service | Status |
|---|---|
| fc-host-agent | 🔲 |
| gui-host-agent | 🔲 |
| Firecracker + jailer | 🔲 |
| Chromium + Playwright | 🔲 |
| WebSocket stream server | 🔲 |

**Resources:**
| Resource | Capacity |
|---|---|
| FC warm VMs | 20 (default pool) |
| GUI concurrent sessions | ~10 |
| Stream bandwidth | 50Mbps per session |

## Runtime Agents Summary

| Agent | Runtime | Node(s) | Pool Size |
|---|---|---|---|
| `wasm-host-agent` | Wasmtime 22 | node2 | Instance pool (100+) |
| `fc-host-agent` | Firecracker 1.8 | node2, node3 | 20 warm VMs each |
| `gui-host-agent` | Chromium 126 | node3 | 5-10 warm sessions |

## Scaling Path

When load increases, migrate from mixed nodes to dedicated pools:

```
Phase 1 (MVP):     3 mixed nodes
Phase 2 (Growth):  2 WASM + 2 FC + 2 GUI = 6 nodes
Phase 3 (Scale):   Autoscaling per pool, multi-region
```
