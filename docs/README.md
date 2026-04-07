# Documentation Portal

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, reviewers, operators, decision-makers |
| Scope | Reader-facing documentation set for the current platform model |
| Last updated | April 8, 2026 |

This directory is the public-facing documentation layer for the repository. It is organized to help a reader answer four questions quickly:

- What is the platform?
- What exists today?
- What is being built next?
- Which historical documents are no longer current?

## Directory structure

| Directory | Purpose |
|---|---|
| `product/` | Tutorials and getting-started guides for new users |
| `process/` | Release notes, test guides, and development process docs |
| `overview/` | Short orientation material for new readers |
| `architecture/` | System diagrams, component relationships, and end-to-end flows |
| `how-to/` | Task-oriented guides for running, deploying, and troubleshooting |
| `reference/` | Stable API, runtime, and tool model references |
| `operations/` | Delivery planning, milestones, and operational readiness documents |
| `archive/` | Superseded documents retained for historical context |

## Recommended reading paths

| Audience | Start here | Then read |
|---|---|---|
| New contributor / integrator | [product/getting-started.md](./product/getting-started.md) | [reference/api-spec.md](./reference/api-spec.md) |
| Architecture review | [architecture/system-overview.md](./architecture/system-overview.md) | [reference/runtime-reference.md](./reference/runtime-reference.md) |
| Delivery and planning | [operations/roadmap.md](./operations/roadmap.md) | [process/release-notes.md](./process/release-notes.md) |
| Hands-on local setup | [how-to/run-locally.md](./how-to/run-locally.md) | [how-to/troubleshooting.md](./how-to/troubleshooting.md) |
| Cluster deployment | [how-to/deploy.md](./how-to/deploy.md) | [architecture/system-overview.md](./architecture/system-overview.md) |
| Writing tests | [process/test-guide.md](./process/test-guide.md) | [reference/runtime-reference.md](./reference/runtime-reference.md) |
| Historical comparison | [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | [architecture/system-overview.md](./architecture/system-overview.md) |

## Document catalog

### Product documentation

| Document | Purpose | Audience |
|---|---|---|
| [product/getting-started.md](./product/getting-started.md) | Step-by-step first-run tutorial: install, start, execute, upload | New contributors, integrators |

### Process documentation

| Document | Purpose | Audience |
|---|---|---|
| [process/release-notes.md](./process/release-notes.md) | Changelog for all platform releases (v0.2.0, v0.1.0) | All |
| [process/test-guide.md](./process/test-guide.md) | How to run tests, test coverage targets, test categories | Contributors |

### API documentation

| Document | Purpose | Audience |
|---|---|---|
| [reference/api-spec.md](./reference/api-spec.md) | Full HTTP API: all endpoints, request/response schemas | Contributors, integrators |

### Architecture and design

| Document | Purpose | Audience |
|---|---|---|
| [overview/platform-overview.md](./overview/platform-overview.md) | One-page orientation: what the platform does, current status | New contributors, reviewers |
| [architecture/system-overview.md](./architecture/system-overview.md) | System diagram, components, request lifecycle, advanced infrastructure | Contributors, reviewers, operators |
| [reference/runtime-reference.md](./reference/runtime-reference.md) | Runtime architecture, topology, and implementation maturity | Contributors, reviewers, operators |
| [reference/tools-reference.md](./reference/tools-reference.md) | Tool model, routing rules, runtime fit | Contributors, platform engineers |

### User guides

| Document | Purpose | Audience |
|---|---|---|
| [how-to/run-locally.md](./how-to/run-locally.md) | Local setup with Python, all env vars, optional features | Contributors, operators |
| [how-to/deploy.md](./how-to/deploy.md) | Cluster bootstrap for the Nomad-based MVP | Operators, contributors |
| [how-to/troubleshooting.md](./how-to/troubleshooting.md) | Common errors, root causes, and fixes | Contributors, operators |

### Operations

| Document | Purpose | Audience |
|---|---|---|
| [operations/roadmap.md](./operations/roadmap.md) | Delivery milestones, dependencies, exit criteria | Delivery owners, contributors |

### Archive

| Document | Purpose |
|---|---|
| [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | Archived Kubernetes-era model, retained for migration context |

## Documentation standards

- Use English for all reader-facing documents.
- Start each active document with status, audience, scope, and last-updated metadata.
- Keep architecture facts in reference documents and milestone commitments in roadmap documents.
- Archive superseded material instead of mixing current and legacy models in the same page.
- Put reader-facing logs or release notes under `docs/` if they need to be published.

## Synchronization contract

Status-bearing public documents must follow a fixed source-of-truth order:

| Document area | Canonical source |
|---|---|
| Current phase, next tasks, blockers | `memory-bank/activeContext.md` |
| Capability and implementation status | `memory-bank/progress.md` |
| Milestone completion and validation | `memory-bank/milestone-timeline.md` |
| Topology and node readiness | `memory-bank/runtime-topology.md` |
| API contract | `sandbox-platform/src/platform_cmd/platform_api.py` and `sandbox-platform/src/sandbox_platform/types.py` |
| Deployment guide | `sandbox-platform/Makefile` and `sandbox-platform/infra/` |

Before updating public docs, normalize the memory-bank status files first. For the contributor workflow and verification order, use `memory-bank/documentation-sync-rules.md`.

Additional repository rules:

- only the root `memory-bank/` is canonical for public status
- `sandbox-platform/memory-bank/` and `sandbox-tools/memory-bank/` are not public status sources
- any done / not-done change must update `docs/operations/roadmap.md` in the same sync pass
- the roadmap checklist is the public at-a-glance view for completed versus pending work

## Internal source material

Internal planning artifacts remain available elsewhere in the repository. Reader-facing documents should summarize stable conclusions rather than lead with internal workflow terminology.
