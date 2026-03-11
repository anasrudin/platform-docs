# Project Brief — Multi-Engine AI Sandbox Platform

## Mission

Build a **multi-engine sandbox platform** that executes untrusted workloads in isolated runtime environments for AI agents.

## Core Architecture

| Component | Role |
|---|---|
| **API Gateway** | Auth, rate limit, tenant routing |
| **Control Plane** | Session, routing, policy, billing, janitor, audit |
| **Tool Registry** | Auto-discovery, skill mapping, health tracking |
| **Nomad Scheduler** | Node placement, resource packing |
| **Host Agents** | Per-node runtime execution (WASM / FC / GUI) |

## Runtime Tiers

| Tier | Engine | Cold Start | Use Case |
|---|---|---|---|
| WASM | Wasmtime 22 | < 5ms | Fast, stateless tools |
| Firecracker | microVM + KVM | 20–80ms (snapshot) | Secure, untrusted code |
| GUI | Chromium + Playwright | ~300ms (warm) | Browser automation |

## Repositories

| Repo | Contents |
|---|---|
| `platform-core` | API Gateway, Control Plane, Tool Registry, Session Manager |
| `platform-runtime` | WASM/FC/GUI runtime, host agents, snapshot builder |

## Key Constraints

- Nomad for orchestration (not Kubernetes)
- 3 separated node pools (WASM / Firecracker / GUI)
- Per-sandbox network isolation (TAP + iptables)
- Per-sandbox filesystem overlay (read-only base + writable layer)
- 5-layer security model (runtime → VM → filesystem → network → host)
- Go 1.23, PostgreSQL 16, Redis/NATS, MinIO

## MVP Target (3 Weeks)

Agent request → execute tool → return result

With: tool registry, runtime router, sandbox execution, artifact storage.
