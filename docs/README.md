# Documentation Portal

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, reviewers, operators, decision-makers |
| Scope | Reader-facing documentation set for the current platform model |
| Last updated | March 11, 2026 |

This directory is the public-facing documentation layer for the repository. It is organized to help a reader answer four questions quickly:

- What is the platform?
- What exists today?
- What is being built next?
- Which historical documents are no longer current?

## Directory structure

| Directory | Purpose |
|---|---|
| `overview/` | Short orientation material for new readers |
| `architecture/` | System diagrams, component relationships, and end-to-end flows |
| `how-to/` | Task-oriented guides for running and validating the platform |
| `reference/` | Stable architecture and tool model references |
| `operations/` | Delivery planning, milestones, and operational readiness documents |
| `archive/` | Superseded documents retained for historical context |

## Recommended reading paths

| Audience | Start here | Then read |
|---|---|---|
| New contributor | [../readme.md](../readme.md) | [overview/platform-overview.md](./overview/platform-overview.md) |
| Architecture review | [architecture/system-overview.md](./architecture/system-overview.md) | [reference/runtime-reference.md](./reference/runtime-reference.md) |
| Delivery and planning | [operations/roadmap.md](./operations/roadmap.md) | [reference/runtime-reference.md](./reference/runtime-reference.md) |
| Hands-on setup | [how-to/run-locally.md](./how-to/run-locally.md) | [reference/api-spec.md](./reference/api-spec.md) |
| Cluster deployment | [how-to/deploy.md](./how-to/deploy.md) | [architecture/system-overview.md](./architecture/system-overview.md) |
| Historical comparison | [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | [architecture/system-overview.md](./architecture/system-overview.md) |

## Document catalog

| Document | Purpose | Primary audience |
|---|---|---|
| [overview/platform-overview.md](./overview/platform-overview.md) | One-page orientation to the platform, scope, and documentation set | New contributors, reviewers |
| [architecture/system-overview.md](./architecture/system-overview.md) | Main system diagram, core components, and request lifecycle | Contributors, reviewers, operators |
| [how-to/deploy.md](./how-to/deploy.md) | Current cluster bootstrap and deployment guide | Operators, contributors |
| [how-to/run-locally.md](./how-to/run-locally.md) | Local startup, validation, and shutdown guide | Contributors, operators |
| [reference/api-spec.md](./reference/api-spec.md) | Current HTTP API contract for the local platform API | Contributors, integrators |
| [reference/openapi.yaml](./reference/openapi.yaml) | OpenAPI representation of the current local API surface | Contributors, integrators |
| [reference/runtime-reference.md](./reference/runtime-reference.md) | Current runtime architecture, deployment shape, and implementation maturity | Contributors, reviewers, operators |
| [reference/tools-reference.md](./reference/tools-reference.md) | Tool model, routing rules, runtime fit, and operational constraints | Contributors, platform engineers |
| [operations/roadmap.md](./operations/roadmap.md) | Current delivery plan, milestones, dependencies, and exit criteria | Delivery owners, contributors |
| [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | Archived Kubernetes-era model retained for migration context | Reviewers, migration planning |

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
| API contract | `sandbox-platform/cmd/platform-api/main.go` and `sandbox-platform/pkg/types/types.go` |
| Deployment guide | `sandbox-platform/Makefile` and `sandbox-platform/infra/` |

Before updating public docs, normalize the memory-bank status files first. For the contributor workflow and verification order, use `memory-bank/documentation-sync-rules.md`.

Additional repository rules:

- only the root `memory-bank/` is canonical for public status
- `sandbox-platform/memory-bank/` and `sandbox-tools/memory-bank/` are not public status sources
- any done / not-done change must update `docs/operations/roadmap.md` in the same sync pass
- the roadmap checklist is the public at-a-glance view for completed versus pending work

## Internal source material

Internal planning artifacts remain available elsewhere in the repository. Reader-facing documents should summarize stable conclusions rather than lead with internal workflow terminology.
