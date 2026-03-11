# Platform Overview

| Field | Value |
|---|---|
| Status | Active |
| Audience | New contributors, reviewers, operators |
| Scope | High-level orientation to the platform and its documentation set |
| Last updated | March 11, 2026 |

## Executive summary

The platform is a multi-runtime execution system designed to run untrusted workloads through specialized runtime paths. It combines a control plane for policy and routing with Nomad for placement and host agents for runtime-specific execution.

The current delivery phase is centered on proving the execution model through a local sandbox, then expanding toward a production-ready system with stronger isolation, artifact handling, and richer control-plane capabilities.

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
- stubbed Firecracker and GUI execution paths with a minimal WASM path
- a documented three-week MVP roadmap

## What comes next

The current roadmap prioritizes:

- Firecracker snapshot-based execution
- real Wasmtime execution
- MinIO-backed artifact handling
- tool registry and skill-based routing
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
