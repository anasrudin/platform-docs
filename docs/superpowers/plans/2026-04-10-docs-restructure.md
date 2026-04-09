# Docs Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `docs/` to Diátaxis quadrants, add MkDocs Material site config, create editorial guide, and bootstrap ADR framework with MADR format.

**Architecture:** Move existing files into four Diátaxis quadrants (`tutorials/`, `how-to/`, `reference/`, `explanation/`) plus utility folders (`decisions/`, `operations/`, `archive/`). Add `mkdocs.yml` at repo root with Material theme and Swagger UI plugin. Create `editorial-guide.md` and MADR-format ADR template + seed ADR.

**Tech Stack:** MkDocs, mkdocs-material, mkdocs-swagger-ui-tag, mkdocs-git-revision-date-localized, mkdocs-minify-html

---

## File map

| Action | Path |
|--------|------|
| `git mv` | `docs/product/getting-started.md` → `docs/tutorials/getting-started.md` |
| `git mv` | `docs/migration/go-to-python.md` → `docs/how-to/migrate-go-to-python.md` |
| `git mv` | `docs/process/test-guide.md` → `docs/how-to/run-tests.md` |
| `git mv` | `docs/overview/platform-overview.md` → `docs/explanation/platform-overview.md` |
| `git mv` | `docs/architecture/system-overview.md` → `docs/explanation/system-overview.md` |
| `git mv` | `docs/architecture/layer-restructure.md` → `docs/explanation/layer-restructure.md` |
| `git mv` | `docs/process/release-notes.md` → `docs/operations/release-notes.md` |
| `git mv` | `docs/todo/` → `docs/archive/todo/` |
| Create | `docs/decisions/README.md` |
| Create | `docs/decisions/template.md` |
| Create | `docs/decisions/001-go-to-python.md` |
| Create | `docs/editorial-guide.md` |
| Create | `mkdocs.yml` (repo root) |
| Create | `requirements-docs.txt` (repo root) |
| Modify | `docs/reference/api-spec.md` — add `<swagger-ui>` tag |
| Modify | `docs/README.md` — update all directory tables and catalog links |
| Modify | `docs/explanation/system-overview.md` — fix 1 relative link |
| Modify | `docs/explanation/platform-overview.md` — fix 4 relative links |
| Modify | `docs/how-to/migrate-go-to-python.md` — fix 1 relative link |
| Modify | `docs/operations/release-notes.md` — fix 1 relative link |
| Modify | `docs/reference/runtime-reference.md` — fix 3 relative links |
| Modify | `docs/how-to/run-locally.md` — fix 1 relative link |
| Remove | `docs/product/`, `docs/migration/`, `docs/process/`, `docs/overview/`, `docs/architecture/` (empty after moves) |

---

## Task 1: Move files into Diátaxis structure

**Files:**
- Create dir: `docs/tutorials/`
- Create dir: `docs/explanation/`
- `git mv` eight files (see steps below)
- Remove: `docs/product/`, `docs/migration/`, `docs/process/`, `docs/overview/`, `docs/architecture/`

- [ ] **Step 1: Create target directories**

```bash
mkdir -p /Users/annas/Desktop/code/platform-docs/docs/tutorials
mkdir -p /Users/annas/Desktop/code/platform-docs/docs/explanation
```

- [ ] **Step 2: Move tutorials content**

```bash
cd /Users/annas/Desktop/code/platform-docs
git mv docs/product/getting-started.md docs/tutorials/getting-started.md
```

- [ ] **Step 3: Move how-to additions**

```bash
git mv docs/migration/go-to-python.md docs/how-to/migrate-go-to-python.md
git mv docs/process/test-guide.md docs/how-to/run-tests.md
```

- [ ] **Step 4: Move explanation content**

```bash
git mv docs/overview/platform-overview.md docs/explanation/platform-overview.md
git mv docs/architecture/system-overview.md docs/explanation/system-overview.md
git mv docs/architecture/layer-restructure.md docs/explanation/layer-restructure.md
```

- [ ] **Step 5: Move operations content**

```bash
git mv docs/process/release-notes.md docs/operations/release-notes.md
```

- [ ] **Step 6: Remove now-empty source directories**

```bash
rmdir docs/product docs/migration docs/process docs/overview docs/architecture
```

- [ ] **Step 7: Verify structure**

```bash
find docs -type f -name "*.md" | grep -v "superpowers\|archive\|todo" | sort
```

Expected output includes:
```
docs/explanation/layer-restructure.md
docs/explanation/platform-overview.md
docs/explanation/system-overview.md
docs/how-to/deploy.md
docs/how-to/migrate-go-to-python.md
docs/how-to/run-locally.md
docs/how-to/run-tests.md
docs/how-to/troubleshooting.md
docs/operations/release-notes.md
docs/operations/roadmap.md
docs/reference/api-spec.md
docs/reference/runtime-reference.md
docs/reference/tools-reference.md
docs/tutorials/getting-started.md
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(docs): restructure folders to Diataxis quadrants"
```

---

## Task 2: Archive todo/

**Files:**
- `git mv`: `docs/todo/` → `docs/archive/todo/`

- [ ] **Step 1: Move todo/ into archive/**

```bash
git mv docs/todo docs/archive/todo
```

- [ ] **Step 2: Verify**

```bash
ls docs/archive/
```

Expected: `legacy-kubernetes-reference.md  todo/`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(docs): archive todo/ planning artifacts"
```

---

## Task 3: Create decisions/ framework

**Files:**
- Create: `docs/decisions/README.md`
- Create: `docs/decisions/template.md`
- Create: `docs/decisions/001-go-to-python.md`

- [ ] **Step 1: Create decisions/ directory**

```bash
mkdir -p /Users/annas/Desktop/code/platform-docs/docs/decisions
```

- [ ] **Step 2: Create decisions/README.md**

Write `docs/decisions/README.md`:

```markdown
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

## Adding a new ADR

1. Copy `template.md` to `NNN-short-slug.md` (zero-padded number, e.g. `002-...`).
2. Fill in all sections. Do not leave any section blank.
3. Set `Status: Proposed` until the decision is ratified.
4. Add a row to the index table above.
5. Commit with message: `docs(adr): add ADR-NNN short title`
```

- [ ] **Step 3: Create decisions/template.md**

Write `docs/decisions/template.md`:

```markdown
---
status: draft
audience: contributors
last_updated: YYYY-MM-DD
---

# ADR-NNN: [Title]

- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNN
- **Date:** YYYY-MM-DD
- **Deciders:** [names or roles]

## Context and problem statement

[1–2 paragraphs: what situation forced this decision, what constraint or requirement exists.]

## Considered options

| Option | Summary |
|--------|---------|
| A | ... |
| B | ... |
| C | ... |

## Decision outcome

**Chosen: Option X** — [one sentence rationale]

### Pros

- ...

### Cons

- ...

## Consequences

[What changes after this decision. What becomes easier. What becomes harder or constrained.]
```

- [ ] **Step 4: Create decisions/001-go-to-python.md**

Write `docs/decisions/001-go-to-python.md`:

```markdown
---
status: active
audience: contributors
last_updated: 2026-04-07
---

# ADR-001: Migrate codebase from Go to Python

- **Status:** Accepted
- **Date:** 2026-04-07
- **Deciders:** platform team

## Context and problem statement

The platform runtime was initially implemented in Go 1.25 across three runtime tiers (WASM, Firecracker microVM, GUI/Chromium). As the platform matured toward data-adjacent workloads and team velocity on Go tooling slowed, a migration was evaluated. Python 3.12+ with FastAPI offered better ecosystem fit for the execution environment, stronger library support for the artifact and queue layers, and reduced operational surface.

The Go implementation had reached a working state (91 tests passing, all three runtimes functional) before the migration decision was made. The decision was not driven by technical failure in Go, but by long-term maintainability and ecosystem alignment.

## Considered options

| Option | Summary |
|--------|---------|
| A | Remain on Go 1.25; continue building runtime features in Go |
| B | Migrate fully to Python 3.12+ with FastAPI + uvicorn |
| C | Polyglot: keep Go for hot-path runtimes, Python for API and orchestration layers |

## Decision outcome

**Chosen: Option B — Full Python migration** — team velocity, ecosystem alignment with data workloads, and lower toolchain complexity outweighed Go's performance advantage at this stage of the platform.

### Pros

- Single language across the entire codebase
- FastAPI + pydantic for typed API contracts with minimal boilerplate
- Strong library ecosystem: structlog, redis-py, minio SDK, httpx
- macOS dev with Linux production via sim/real mode split for Firecracker
- 91/91 tests ported and passing after migration

### Cons

- Python is slower than Go for CPU-bound work; acceptable at current scale
- Runtime-level concurrency model differs (asyncio vs goroutines)
- Migration required rewriting all service entry points and test suite

## Consequences

All new platform services must be written in Python 3.12+. The Go toolchain is no longer required. The `src/sandbox_platform/` package is the canonical implementation. Entry points live in `src/platform_cmd/`. Feature flags (`CONSUL_ENABLED`, `SCALER_ENABLED`, `MTLS_ENABLED`) default to off for safe local development. See `how-to/migrate-go-to-python.md` for the full migration record.
```

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/
git commit -m "docs(adr): bootstrap decisions/ with MADR template and ADR-001 Go-to-Python"
```

---

## Task 4: Create editorial-guide.md

**Files:**
- Create: `docs/editorial-guide.md`

- [ ] **Step 1: Write docs/editorial-guide.md**

```markdown
---
status: active
audience: contributors
last_updated: 2026-04-10
---

# Editorial guide

This guide defines tone, formatting, and structure rules for all documents in
`tutorials/`, `how-to/`, `reference/`, and `explanation/`. Follow these rules
when writing or reviewing documentation.

## Voice and tense

Use active voice and present tense.

| Correct | Incorrect |
|---------|-----------|
| "Run the command." | "The command should be run." |
| "The API returns a session ID." | "The API will return a session ID." |
| "You configure the agent with..." | "The user configures the agent with..." |

Write in second person. Address the reader as "you", not "the user" or "one".

## Headings

Use sentence case. Capitalize only the first word and proper nouns.

| Correct | Incorrect |
|---------|-----------|
| "Getting started" | "Getting Started" |
| "Run the platform locally" | "Run The Platform Locally" |
| "Firecracker runtime" | "firecracker runtime" |

Headings must describe content, not introduce it. Avoid "Overview",
"Introduction", and "About X" as standalone headings.

## Paragraphs and lists

One idea per paragraph. Cut if it runs longer than four sentences.

Use lists for three or more parallel items. All list items must start with the
same grammatical form — typically an imperative verb in how-to guides, a noun
phrase in reference docs.

## Code formatting

Put all commands, file paths, and values in code formatting.

- Inline: use backticks — `mkdocs serve`
- Multi-line or runnable: use a fenced code block with a language tag

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Never write commands in plain prose.

## Admonitions

Use MkDocs Material admonition blocks. Do not use "Please note that..." or
"IMPORTANT!!!".

```
!!! note
    This applies only when CONSUL_ENABLED=true.

!!! warning
    Stopping the cluster mid-migration corrupts session state.

!!! tip
    Use FC_MODE=sim for local development on macOS.
```

## Document metadata

Every active document must include this frontmatter block at the top:

```yaml
---
status: active
audience: contributors | operators | integrators | all
last_updated: YYYY-MM-DD
---
```

Set `status: archived` for documents in `archive/`. Set `status: draft` for
incomplete documents.

## Section-specific tone

| Section | Tone |
|---------|------|
| `tutorials/` | Encouraging and step-by-step. No assumed prior knowledge of this platform. |
| `how-to/` | Direct and task-focused. Assumes the reader knows the platform basics. |
| `reference/` | Neutral and precise. No opinions, no narrative. Describe what exists. |
| `explanation/` | Analytical. May include trade-offs, history, and design rationale. |

## What to avoid

- Filler phrases: "This guide will walk you through...", "In this section, we will..."
- Redundant context: do not restate the heading in the first sentence
- Future tense for current behavior: "will return" → "returns"
- Passive constructions: "is used to" → use, "can be configured" → configure
```

- [ ] **Step 2: Commit**

```bash
git add docs/editorial-guide.md
git commit -m "docs: add Google-style editorial guide"
```

---

## Task 5: Create mkdocs.yml and requirements-docs.txt

**Files:**
- Create: `mkdocs.yml` (repo root)
- Create: `requirements-docs.txt` (repo root)

- [ ] **Step 1: Write mkdocs.yml at repo root**

```yaml
site_name: Platform Docs
site_description: Sandbox execution platform — tutorials, reference, and architecture docs
docs_dir: docs
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.top
    - search.suggest
    - content.code.copy
  palette:
    - scheme: default
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

plugins:
  - search
  - swagger-ui-tag
  - git-revision-date-localized:
      enable_creation_date: true
  - minify:
      minify_html: true

nav:
  - Home: README.md
  - Tutorials:
      - Getting started: tutorials/getting-started.md
  - How-to guides:
      - Run locally: how-to/run-locally.md
      - Deploy to cluster: how-to/deploy.md
      - Run tests: how-to/run-tests.md
      - Migrate Go to Python: how-to/migrate-go-to-python.md
      - Troubleshooting: how-to/troubleshooting.md
  - Reference:
      - API spec: reference/api-spec.md
      - Runtime reference: reference/runtime-reference.md
      - Tools reference: reference/tools-reference.md
  - Explanation:
      - Platform overview: explanation/platform-overview.md
      - System overview: explanation/system-overview.md
      - Layer restructure: explanation/layer-restructure.md
  - Decisions:
      - Index: decisions/README.md
      - "ADR-001 — Go to Python": decisions/001-go-to-python.md
  - Operations:
      - Roadmap: operations/roadmap.md
      - Release notes: operations/release-notes.md
  - Archive:
      - Legacy Kubernetes reference: archive/legacy-kubernetes-reference.md
```

- [ ] **Step 2: Write requirements-docs.txt at repo root**

```
mkdocs-material>=9.0
mkdocs-swagger-ui-tag>=0.6
mkdocs-git-revision-date-localized>=1.2
mkdocs-minify-html>=0.1
```

- [ ] **Step 3: Commit**

```bash
git add mkdocs.yml requirements-docs.txt
git commit -m "feat(docs): add MkDocs Material config with Swagger UI and git-date plugins"
```

---

## Task 6: Add swagger-ui tag to reference/api-spec.md

**Files:**
- Modify: `docs/reference/api-spec.md`

- [ ] **Step 1: Read the current top of api-spec.md**

Open `docs/reference/api-spec.md` and find the section that describes API endpoints. The swagger-ui tag goes after the introductory paragraph, before the first endpoint section.

- [ ] **Step 2: Add the swagger-ui render tag**

Find the first `## ` heading in `docs/reference/api-spec.md` (e.g., `## Endpoints` or similar). Insert this block immediately before it:

```markdown
## Interactive API reference

<swagger-ui src="../openapi.yaml"/>

---
```

This renders the full OpenAPI spec as interactive Swagger UI when served via `mkdocs serve`. The relative path `../openapi.yaml` resolves correctly from `reference/api-spec.md` to `reference/openapi.yaml`.

- [ ] **Step 3: Commit**

```bash
git add docs/reference/api-spec.md
git commit -m "docs(reference): add swagger-ui interactive render to api-spec"
```

---

## Task 7: Update docs/README.md

**Files:**
- Modify: `docs/README.md`

This file has the directory structure table, recommended reading paths, and document catalog — all with old folder paths. Replace the entire file with the updated version below.

- [ ] **Step 1: Replace docs/README.md**

Write the following content to `docs/README.md`:

```markdown
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
| [explanation/layer-restructure.md](./explanation/layer-restructure.md) | Layer architecture changes and reasoning | Contributors, reviewers |

### Architecture decisions

| Document | Purpose | Audience |
|---|---|---|
| [decisions/README.md](./decisions/README.md) | ADR index | All |
| [decisions/001-go-to-python.md](./decisions/001-go-to-python.md) | Go → Python migration decision record | Contributors |

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
| API contract | `sandbox-platform/src/platform_cmd/platform_api.py` and `sandbox-platform/src/sandbox_platform/types.py` |
| Deployment guide | `sandbox-platform/Makefile` and `sandbox-platform/infra/` |

Before updating public docs, ensure the source-of-truth files are current first.
```

- [ ] **Step 2: Commit**

```bash
git add docs/README.md
git commit -m "docs: update README for Diataxis structure and new folder paths"
```

---

## Task 8: Fix cross-references in moved and affected files

**Files:**
- Modify: `docs/explanation/system-overview.md` — 1 link
- Modify: `docs/explanation/platform-overview.md` — 4 links
- Modify: `docs/how-to/migrate-go-to-python.md` — 1 link
- Modify: `docs/operations/release-notes.md` — 1 link
- Modify: `docs/reference/runtime-reference.md` — 3 links
- Modify: `docs/how-to/run-locally.md` — 1 link

- [ ] **Step 1: Fix explanation/system-overview.md**

Line 232 changes from `../overview/platform-overview.md` to `./platform-overview.md`
(both files are now in `explanation/`).

Open `docs/explanation/system-overview.md` and replace:
```
[../overview/platform-overview.md](../overview/platform-overview.md)
```
with:
```
[./platform-overview.md](./platform-overview.md)
```

- [ ] **Step 2: Fix explanation/platform-overview.md**

Four links need updating. Open `docs/explanation/platform-overview.md` and apply:

| Old | New |
|-----|-----|
| `[../product/getting-started.md](../product/getting-started.md)` | `[../tutorials/getting-started.md](../tutorials/getting-started.md)` |
| `[../architecture/system-overview.md](../architecture/system-overview.md)` | `[./system-overview.md](./system-overview.md)` |
| `[../process/release-notes.md](../process/release-notes.md)` | `[../operations/release-notes.md](../operations/release-notes.md)` |
| `[../process/test-guide.md](../process/test-guide.md)` | `[../how-to/run-tests.md](../how-to/run-tests.md)` |

- [ ] **Step 3: Fix how-to/migrate-go-to-python.md**

Line 22 changes `../how-to/run-locally.md` → `./run-locally.md`
(both files are now in `how-to/`).

Open `docs/how-to/migrate-go-to-python.md` and replace:
```
[../how-to/run-locally.md](../how-to/run-locally.md)
```
with:
```
[./run-locally.md](./run-locally.md)
```

- [ ] **Step 4: Fix operations/release-notes.md**

Line 148 changes `../migration/go-to-python.md` → `../how-to/migrate-go-to-python.md`.

Open `docs/operations/release-notes.md` and replace:
```
[../migration/go-to-python.md](../migration/go-to-python.md)
```
with:
```
[../how-to/migrate-go-to-python.md](../how-to/migrate-go-to-python.md)
```

- [ ] **Step 5: Fix reference/runtime-reference.md**

Three links need updating. Open `docs/reference/runtime-reference.md` and apply:

| Old | New |
|-----|-----|
| `[../overview/platform-overview.md](../overview/platform-overview.md)` | `[../explanation/platform-overview.md](../explanation/platform-overview.md)` |
| `[../architecture/system-overview.md](../architecture/system-overview.md)` | `[../explanation/system-overview.md](../explanation/system-overview.md)` |
| `[../product/getting-started.md](../product/getting-started.md)` | `[../tutorials/getting-started.md](../tutorials/getting-started.md)` |

- [ ] **Step 6: Fix how-to/run-locally.md**

Line 169 changes `../architecture/system-overview.md` → `../explanation/system-overview.md`.

Open `docs/how-to/run-locally.md` and replace:
```
[../architecture/system-overview.md](../architecture/system-overview.md)
```
with:
```
[../explanation/system-overview.md](../explanation/system-overview.md)
```

- [ ] **Step 7: Commit**

```bash
git add docs/explanation/system-overview.md \
        docs/explanation/platform-overview.md \
        docs/how-to/migrate-go-to-python.md \
        docs/operations/release-notes.md \
        docs/reference/runtime-reference.md \
        docs/how-to/run-locally.md
git commit -m "docs: fix cross-references after Diataxis folder restructure"
```

---

## Task 9: Verify with mkdocs build

**Files:** none created or modified — verification only

- [ ] **Step 1: Install docs dependencies**

```bash
cd /Users/annas/Desktop/code/platform-docs
pip install -r requirements-docs.txt
```

Expected: all four packages install without errors.

- [ ] **Step 2: Build the site**

```bash
mkdocs build --strict 2>&1 | head -50
```

Expected: `INFO - Documentation built in X.XX seconds` with no `WARNING` or `ERROR` lines.

Common failures and fixes:
- `WARNING - Doc file ... not found in nav` → add the missing file to the `nav:` section in `mkdocs.yml`
- `WARNING - ... contains a link to ... not found` → a cross-reference was missed in Task 8; fix the link
- `ERROR - Config value 'plugins': The "swagger-ui-tag" plugin is not installed` → rerun `pip install -r requirements-docs.txt`

- [ ] **Step 3: Spot-check the interactive OpenAPI render**

```bash
mkdocs serve &
```

Open `http://127.0.0.1:8000/reference/api-spec/` in a browser. The Swagger UI component must render (shows endpoint list, not raw YAML).

Kill the server after verifying: `kill %1`

- [ ] **Step 4: Commit any fixes found during verification**

```bash
git add -A
git commit -m "docs: fix mkdocs build warnings from strict verification"
```

Only commit if there were actual fixes. Skip this step if the build was clean.
