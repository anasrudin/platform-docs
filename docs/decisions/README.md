---
status: active
audience: contributors
last_updated: 2026-04-10
---

# Architecture decision records

This directory contains Architecture Decision Records (ADRs) for the platform.
ADRs document significant technical decisions: what was decided, why, and what the consequences are.

## Format

ADRs use [MADR](https://adr.github.io/madr/) (Markdown Architectural Decision Records).
Use `template.md` when creating a new ADR.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](001-go-to-python.md) | Migrate codebase from Go to Python | Accepted | 2026-04-07 |
| [002](002-nomad-worker-architecture.md) | Migrate to Nomad Worker architecture | Accepted | 2026-04-09 |

## Adding a new ADR

1. Copy `template.md` to `NNN-short-slug.md` (zero-padded number, e.g. `003-...`).
2. Fill in all sections. Do not leave any section blank.
3. Set `Status: Proposed` until the decision is ratified.
4. Add a row to the index table above.
5. Commit with message: `docs(adr): add ADR-NNN short title`
