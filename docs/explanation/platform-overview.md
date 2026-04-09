# Platform Overview

| Field | Value |
|---|---|
| Status | Active |
| Audience | New contributors, reviewers, operators |
| Scope | High-level orientation to the platform and its documentation set |
| Last updated | April 8, 2026 |

## Executive summary

Sandbox Platform is a multi-runtime execution system for running untrusted workloads in isolated environments. It combines a Python-based control plane (FastAPI) with Nomad for job placement, Consul for service discovery, HAProxy for load balancing, and Firecracker microVMs, WASM, and GUI runtimes for execution isolation.

The Week 1 runtime foundation is complete. Five advanced feature phases have shipped: Consul service discovery, HAProxy load balancing, auto-scaling, package management, and mutual TLS. All 235 unit tests pass.

## What the platform does

| Runtime | Primary purpose | Startup |
|---|---|---|
| WASM | Fast, bounded, stateless tool execution | < 5 ms |
| Firecracker | Secure compute for untrusted code | 20–80 ms from snapshot |
| GUI (Chromium) | Browser automation and visual workflows | ~300 ms warm |

A caller submits an execution request to the API with a tool name and input. The platform routes the job to the right runtime, executes it in an isolated environment, and returns structured output. Artifacts, snapshots, and package wheels are persisted in MinIO and survive the sandbox lifecycle.

## What exists today

| Area | Status |
|---|---|
| Python 3.12+ codebase (FastAPI, psycopg2, redis-py, minio) | Complete |
| Firecracker runtime (pool, snapshot restore, guest transport) | Complete — real + sim mode |
| WASM runtime (Wasmtime CLI, MinIO module cache) | Complete — real + sim mode |
| GUI runtime | Stub — sim mode only |
| HTTP API (health, sessions, execute, artifacts, packages) | Complete |
| Consul service discovery and session KV | Complete — opt-in |
| HAProxy load balancing with consul-template | Complete — infra templates available |
| Auto-scaling (metrics, policy, Nomad API) | Complete — opt-in |
| Package management (pip download, MinIO cache) | Complete — opt-in |
| Mutual TLS (TLS 1.3, ECDSA P-256, cert rotation) | Complete — opt-in |
| Unit test suite (235 tests, ≥ 95% coverage on new code) | Complete |

## What is not yet implemented

- Package install executed inside a Firecracker VM session (currently host-only)
- Auto-scaler node list dynamically populated from Consul (currently empty)
- mTLS on outbound calls (agent → Consul, scaler → Nomad)
- `PUT /packages/{name}` and `GET /packages/{name}` endpoints
- API authentication and rate limiting
- Tool registry API
- GUI runtime hardening

## Documentation entry points

| Need | Document |
|---|---|
| First run — install, start, execute | [../product/getting-started.md](../product/getting-started.md) |
| Full system architecture | [../architecture/system-overview.md](../architecture/system-overview.md) |
| All HTTP API endpoints | [../reference/api-spec.md](../reference/api-spec.md) |
| Runtime internals and tiers | [../reference/runtime-reference.md](../reference/runtime-reference.md) |
| Run locally (Python) | [../how-to/run-locally.md](../how-to/run-locally.md) |
| Deploy to a cluster | [../how-to/deploy.md](../how-to/deploy.md) |
| Diagnose problems | [../how-to/troubleshooting.md](../how-to/troubleshooting.md) |
| Changelog | [../process/release-notes.md](../process/release-notes.md) |
| Test guide | [../process/test-guide.md](../process/test-guide.md) |
| Delivery milestones | [../operations/roadmap.md](../operations/roadmap.md) |
