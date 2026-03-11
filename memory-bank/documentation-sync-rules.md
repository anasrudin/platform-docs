# Documentation Sync Rules

> Last updated: 2026-03-11

## Purpose

This file defines the synchronization contract between the memory bank, the codebase, and the public documentation layer in `docs/`.

The goal is simple: status-bearing documents should not drift.

## Canonical scope

The only canonical status source for this repository is the root `memory-bank/` directory.

Use these files as source of truth:

- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/milestone-timeline.md`
- `memory-bank/runtime-topology.md`

Do not use these as canonical inputs for public docs:

- `sandbox-platform/memory-bank/`
- `sandbox-tools/memory-bank/`

Those subproject memory-bank directories may contain older or scoped copies, but they do not control the public documentation in `docs/`.

## Canonical source matrix

| Topic | Canonical source |
|---|---|
| Current phase, current focus, next tasks, blockers | `activeContext.md` |
| Capability and implementation status | `progress.md` |
| Milestone status and validation checklist | `milestone-timeline.md` |
| Node roles and topology readiness | `runtime-topology.md` |
| API behavior and payloads | `sandbox-platform/cmd/platform-api/main.go`, `sandbox-platform/pkg/types/types.go` |
| Deployment steps and supported rollout path | `sandbox-platform/Makefile`, `sandbox-platform/infra/` |

## Update order

When implementation status changes, update files in this order:

1. `memory-bank/activeContext.md`
2. `memory-bank/progress.md`
3. `memory-bank/milestone-timeline.md`
4. `memory-bank/runtime-topology.md` if topology or readiness changed
5. public documents under `docs/`

## Always-sync rule

Any change that affects delivery status, implementation maturity, topology readiness, or supported operator workflow is incomplete until the matching public docs are updated in the same change.

At minimum:

- update the root `memory-bank/` files first
- update the relevant human-facing document in `docs/`
- update `docs/operations/roadmap.md` when the change affects done / not-done status
- keep `Last updated` metadata aligned with the date of the sync pass

If you cannot safely update both the memory bank and the public docs in the same pass, leave the status unchanged and note the gap explicitly.

## Synchronization gates

Do not mark work complete in public docs unless the matching memory-bank files agree.

Required agreement rules:

- A day or week milestone is complete only if `activeContext.md`, `progress.md`, and `milestone-timeline.md` all reflect that state.
- A runtime is considered real only if `progress.md` and the implementation code both support that claim.
- API docs may only describe endpoints that exist in `platform-api` and matching types.
- Deployment docs may only describe flows backed by the existing Make targets and infra scripts.
- If code-level defaults and bootstrap scripts disagree, document the mismatch explicitly until the implementation is unified.
- The public roadmap checklist in `docs/operations/roadmap.md` must match the milestone and validation state in `memory-bank/milestone-timeline.md`.
- `docs/README.md` must continue to describe the root `memory-bank/` as the status source for public docs.

## Public-doc mappings

| Public document | Derived from |
|---|---|
| `docs/operations/roadmap.md` | `activeContext.md`, `progress.md`, `milestone-timeline.md` |
| `docs/reference/runtime-reference.md` | `activeContext.md`, `progress.md`, `runtime-topology.md` |
| `docs/reference/api-spec.md` and `docs/reference/openapi.yaml` | `platform-api/main.go`, `pkg/types/types.go` |
| `docs/how-to/deploy.md` | `Makefile`, `infra/nomad/`, `infra/scripts/`, `infra/minio/`, `infra/postgres/` |
| `docs/how-to/run-locally.md` | `Makefile`, runtime implementations, and current local API behavior |

## Verification checklist

Before closing a status-sync pass, verify:

- public roadmap status matches `activeContext.md`
- runtime maturity in public reference matches `progress.md`
- milestone completion in public roadmap matches `milestone-timeline.md`
- topology claims match `runtime-topology.md`
- API surface matches `platform-api/main.go`
- the roadmap checkboxes clearly distinguish complete vs not complete work for a human reader
- no public doc relies on `sandbox-platform/memory-bank/` or `sandbox-tools/memory-bank/` as status sources

## Contributor note

If two memory-bank files disagree, fix the memory bank first. Public docs should never become the tie-breaker for implementation state.
