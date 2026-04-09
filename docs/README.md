# Documentation portal

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, reviewers, operators, decision-makers |
| Scope | Reader-facing documentation set for the current platform model |
| Last updated | 2026-04-10 |

This directory is the public-facing documentation layer for the repository.
It is organized using the [Diátaxis](https://diataxis.fr/) framework to help
a reader answer four questions quickly:

- What is the platform?
- How do I do a specific task?
- What is the exact API or runtime contract?
- Why does it work this way?

## Directory structure

| Directory | Diátaxis type | Purpose |
|---|---|---|
| `tutorials/` | Tutorials | Step-by-step learning experiences for new users |
| `how-to/` | How-to guides | Task-oriented guides for specific goals |
| `reference/` | Reference | Stable API, runtime, and tool model descriptions |
| `explanation/` | Explanation | System architecture, design rationale, context |
| `decisions/` | — | Architecture Decision Records (MADR format) |
| `operations/` | — | Delivery planning, roadmap, release notes |
| `archive/` | — | Superseded documents retained for historical context |

## Recommended reading paths

| Audience | Start here | Then read |
|---|---|---|
| New contributor / integrator | [tutorials/getting-started.md](./tutorials/getting-started.md) | [reference/api-spec.md](./reference/api-spec.md) |
| Architecture review | [explanation/system-overview.md](./explanation/system-overview.md) | [reference/runtime-reference.md](./reference/runtime-reference.md) |
| Delivery and planning | [operations/roadmap.md](./operations/roadmap.md) | [operations/release-notes.md](./operations/release-notes.md) |
| Hands-on local setup | [how-to/run-locally.md](./how-to/run-locally.md) | [how-to/troubleshooting.md](./how-to/troubleshooting.md) |
| Cluster deployment | [how-to/deploy.md](./how-to/deploy.md) | [explanation/system-overview.md](./explanation/system-overview.md) |
| Writing tests | [how-to/run-tests.md](./how-to/run-tests.md) | [reference/runtime-reference.md](./reference/runtime-reference.md) |
| Historical comparison | [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | [explanation/system-overview.md](./explanation/system-overview.md) |

## Document catalog

### Tutorials

| Document | Purpose | Audience |
|---|---|---|
| [tutorials/getting-started.md](./tutorials/getting-started.md) | Step-by-step first-run: install, start, execute, upload | New contributors, integrators |

### How-to guides

| Document | Purpose | Audience |
|---|---|---|
| [how-to/run-locally.md](./how-to/run-locally.md) | Local setup with Python, all env vars, optional features | Contributors, operators |
| [how-to/deploy.md](./how-to/deploy.md) | Cluster bootstrap for the Nomad-based MVP | Operators, contributors |
| [how-to/run-tests.md](./how-to/run-tests.md) | How to run tests, coverage targets, test categories | Contributors |
| [how-to/migrate-go-to-python.md](./how-to/migrate-go-to-python.md) | Shell commands and steps for the Go → Python migration | Contributors |
| [how-to/troubleshooting.md](./how-to/troubleshooting.md) | Common errors, root causes, and fixes | Contributors, operators |

### Reference

| Document | Purpose | Audience |
|---|---|---|
| [reference/api-spec.md](./reference/api-spec.md) | Full HTTP API: all endpoints, request/response schemas | Contributors, integrators |
| [reference/runtime-reference.md](./reference/runtime-reference.md) | Runtime architecture, topology, and implementation maturity | Contributors, reviewers, operators |
| [reference/tools-reference.md](./reference/tools-reference.md) | Tool model, routing rules, runtime fit | Contributors, platform engineers |

### Explanation

| Document | Purpose | Audience |
|---|---|---|
| [explanation/platform-overview.md](./explanation/platform-overview.md) | One-page orientation: what the platform does, current status | New contributors, reviewers |
| [explanation/system-overview.md](./explanation/system-overview.md) | System diagram, components, request lifecycle, advanced infrastructure | Contributors, reviewers, operators |

### Architecture decisions

| Document | Purpose | Audience |
|---|---|---|
| [decisions/README.md](./decisions/README.md) | ADR index | All |
| [decisions/001-go-to-python.md](./decisions/001-go-to-python.md) | Go → Python migration decision record | Contributors |
| [decisions/002-nomad-worker-architecture.md](./decisions/002-nomad-worker-architecture.md) | Migrate to Nomad Worker architecture | Contributors |

### Operations

| Document | Purpose | Audience |
|---|---|---|
| [operations/roadmap.md](./operations/roadmap.md) | Delivery milestones, dependencies, exit criteria | Delivery owners, contributors |
| [operations/release-notes.md](./operations/release-notes.md) | Changelog for all platform releases | All |

### Archive

| Document | Purpose |
|---|---|
| [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | Archived Kubernetes-era model, retained for migration context |

## Documentation standards

See [editorial-guide.md](./editorial-guide.md) for full tone, formatting, and
metadata rules.

Summary:
- Use English for all reader-facing documents.
- Start each active document with YAML frontmatter: `status`, `audience`, `last_updated`.
- Keep architecture facts in `explanation/` and `reference/`; milestone commitments in `operations/`.
- Archive superseded material instead of mixing current and legacy models in the same page.
- Add new ADRs under `decisions/` and update the ADR index.

## Synchronization contract

Status-bearing public documents must follow a fixed source-of-truth order:

| Document area | Canonical source |
|---|---|
| API contract | `sandbox-worker/src/api/` and `sandbox-worker/src/models/` |
| Deployment guide | `sandbox-worker/` Makefile and `services/` infra |

Before updating public docs, ensure the source-of-truth files are current first.
