# Platform Overview

| Field | Value |
|---|---|
| Status | Active |
| Audience | New contributors, reviewers, operators |
| Scope | High-level orientation to the platform and its documentation set |
| Last updated | March 11, 2026 |

## Executive summary

The platform is a multi-runtime execution system designed to run untrusted workloads through specialized runtime paths. It combines a control plane for policy and routing with Nomad for placement and host agents for runtime-specific execution.

Week 1 runtime foundation is complete. The current delivery phase is now centered on control-plane capabilities such as auth, rate limiting, discovery, and monitoring, while preserving the completed runtime foundation as the baseline for future isolation and GUI work.

## What the platform does

The platform supports three execution tiers:

| Runtime | Primary purpose |
|---|---|
| WASM | Fast, bounded, mostly stateless tool execution |
| Firecracker | Secure execution for untrusted code and heavier compute |
| GUI | Browser automation and interactive workflows |

## What exists today

- a reader-facing documentation set under `docs/`
- a local sandbox under `sandbox-platform/`
- minimal API, session, and routing behavior for local validation
- real Firecracker and WASM execution paths with development-environment fallbacks
- artifact, snapshot, and module flows backed by MinIO integration
- a stubbed GUI execution path
- a documented three-week MVP roadmap

## What comes next

The current roadmap prioritizes:

- API gateway authentication and rate limiting
- tool registry and skill-based routing
- observability through Prometheus and Grafana
- GUI execution hardening and isolation

Use [../operations/roadmap.md](../operations/roadmap.md) for the milestone plan and [../architecture/system-overview.md](../architecture/system-overview.md) for the end-to-end system view.

## Documentation entry points

| Need | Document |
|---|---|
| Understand the full system shape | [../architecture/system-overview.md](../architecture/system-overview.md) |
| Review current runtime facts | [../reference/runtime-reference.md](../reference/runtime-reference.md) |
| Review the tool model | [../reference/tools-reference.md](../reference/tools-reference.md) |
| Review the HTTP API | [../reference/api-spec.md](../reference/api-spec.md) |
| Run the platform locally | [../how-to/run-locally.md](../how-to/run-locally.md) |
| Deploy the MVP environment | [../how-to/deploy.md](../how-to/deploy.md) |
| Review delivery milestones | [../operations/roadmap.md](../operations/roadmap.md) |

## Non-goals for this document

- detailed runtime internals
- operational procedures
- historical design comparison

Those topics belong in architecture, how-to, operations, and archive documents.
