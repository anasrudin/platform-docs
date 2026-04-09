# Design: Docs Restructure to Diátaxis + MkDocs

- **Status:** Approved
- **Date:** 2026-04-10
- **Scope:** `docs/` folder restructure, MkDocs site config, editorial guide, ADR framework

## Overview

Restructure the existing `docs/` directory to follow the Diátaxis documentation framework, add a MkDocs site with Material theme (full-featured), enforce Google-style editorial rules, integrate OpenAPI rendering, and introduce MADR-format ADRs for technical decisions.

## 1. Folder Structure

### New layout (Diátaxis + utility folders)

```
docs/
  tutorials/
    getting-started.md
  how-to/
    run-locally.md
    deploy.md
    troubleshooting.md
    migrate-go-to-python.md
    run-tests.md
  reference/
    api-spec.md
    openapi.yaml
    runtime-reference.md
    tools-reference.md
  explanation/
    platform-overview.md
    system-overview.md
    layer-restructure.md
  decisions/
    README.md
    template.md
    001-go-to-python.md
  operations/
    roadmap.md
    release-notes.md
  archive/
    legacy-kubernetes-reference.md
    todo/
      phase-2.md
      phase-3.md
      todo-list.md
  editorial-guide.md
  README.md

mkdocs.yml                     (repo root)
```

### File migration map

| Old path | New path | Reason |
|----------|----------|--------|
| `product/getting-started.md` | `tutorials/getting-started.md` | Diátaxis: Tutorials |
| `how-to/run-locally.md` | `how-to/run-locally.md` | Diátaxis: How-to (unchanged) |
| `how-to/deploy.md` | `how-to/deploy.md` | Diátaxis: How-to (unchanged) |
| `how-to/troubleshooting.md` | `how-to/troubleshooting.md` | Diátaxis: How-to (unchanged) |
| `migration/go-to-python.md` | `how-to/migrate-go-to-python.md` | Task-oriented → How-to |
| `process/test-guide.md` | `how-to/run-tests.md` | Task-oriented → How-to |
| `overview/platform-overview.md` | `explanation/platform-overview.md` | Diátaxis: Explanation |
| `architecture/system-overview.md` | `explanation/system-overview.md` | Diátaxis: Explanation |
| `architecture/layer-restructure.md` | `explanation/layer-restructure.md` | Diátaxis: Explanation |
| `reference/api-spec.md` | `reference/api-spec.md` | Diátaxis: Reference (unchanged) |
| `reference/openapi.yaml` | `reference/openapi.yaml` | Reference (unchanged) |
| `reference/runtime-reference.md` | `reference/runtime-reference.md` | Reference (unchanged) |
| `reference/tools-reference.md` | `reference/tools-reference.md` | Reference (unchanged) |
| `process/release-notes.md` | `operations/release-notes.md` | Operational artifact |
| `operations/roadmap.md` | `operations/roadmap.md` | Operations (unchanged) |
| `archive/legacy-kubernetes-reference.md` | `archive/legacy-kubernetes-reference.md` | Archive (unchanged) |
| `todo/` | `archive/todo/` | Internal planning, retained for history |

### Diátaxis quadrant definitions (for this project)

| Section | Purpose | Reader question answered |
|---------|---------|--------------------------|
| `tutorials/` | Learning-oriented. Guides the reader through a complete experience. | "How do I learn this?" |
| `how-to/` | Task-oriented. Addresses a specific goal. Assumes prior knowledge. | "How do I do X?" |
| `reference/` | Information-oriented. Accurate, complete, neutral descriptions. | "What is X exactly?" |
| `explanation/` | Understanding-oriented. Discusses, clarifies, provides context. | "Why does X work this way?" |

`decisions/`, `operations/`, and `archive/` are utility folders — outside the four quadrants.

## 2. MkDocs Configuration

### `mkdocs.yml` (repo root)

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
      - "001 — Go to Python": decisions/001-go-to-python.md
  - Operations:
      - Roadmap: operations/roadmap.md
      - Release notes: operations/release-notes.md
  - Archive:
      - Legacy Kubernetes reference: archive/legacy-kubernetes-reference.md
```

### OpenAPI rendering

In `reference/api-spec.md`, add at the top of the interactive section:

```markdown
<swagger-ui src="../openapi.yaml"/>
```

### Python dependencies

Create `requirements-docs.txt` at repo root (alongside `mkdocs.yml`):

```
mkdocs-material>=9.0
mkdocs-swagger-ui-tag>=0.6
mkdocs-git-revision-date-localized>=1.2
mkdocs-minify-html>=0.1
```

Install with: `pip install -r requirements-docs.txt`

This is separate from `sandbox-platform/pyproject.toml` — docs tooling is a repo-level concern, not part of the platform package.

## 3. Editorial Guide

File: `docs/editorial-guide.md`

Applies to all documents in `tutorials/`, `how-to/`, `reference/`, and `explanation/`.

### Core rules (Google Developer Documentation Style)

| Rule | Correct | Incorrect |
|------|---------|-----------|
| Active voice | "Run the command" | "The command should be run" |
| Present tense | "The API returns a session ID" | "The API will return a session ID" |
| Second person | "You configure the agent" | "The user configures the agent" |
| Sentence case headings | "Getting started" | "Getting Started" |
| Parallel list items | All start with an imperative verb | Mixed verb forms |
| No filler | "This guide shows how to deploy." | "This comprehensive guide will walk you through..." |
| Code formatting | Inline commands in backticks; blocks in fenced code | Plain text for commands |
| Admonitions | `!!! note`, `!!! warning`, `!!! tip` | "Please note that...", "IMPORTANT!!!" |
| Paragraph length | One idea per paragraph, max 4 sentences | Long multi-topic paragraphs |

### Document metadata header

Every active document must start with:

```markdown
---
status: active | draft | archived
audience: contributors | operators | integrators | all
last_updated: YYYY-MM-DD
---
```

### Section-specific tone

| Section | Tone |
|---------|------|
| Tutorials | Encouraging, step-by-step, no assumed context |
| How-to | Direct, task-focused, assumes reader knows the platform |
| Reference | Neutral, precise, no opinions |
| Explanation | Analytical, reasoned, may include trade-offs |

## 4. ADR Framework

### Format: MADR (Markdown Architectural Decision Records)

File naming: `decisions/NNN-short-slug.md` (zero-padded, e.g. `001`, `002`).

### Template (`docs/decisions/template.md`)

```markdown
# ADR-NNN: [Title]

- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNN
- **Date:** YYYY-MM-DD
- **Deciders:** [names or roles]

## Context and problem statement

[1–2 paragraphs: what situation forced this decision, what constraint or requirement exists]

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

### Seed ADR: `001-go-to-python.md`

Documents the April 2026 decision to migrate the platform codebase from Go 1.25 to Python 3.12+, with FastAPI + uvicorn. Key context: tooling fit, team velocity, ecosystem alignment with data-adjacent workloads. Decision: accepted. Consequences: all future services in Python; Go toolchain no longer required.

### `decisions/README.md`

ADR index table: number, title, status, date. Updated each time a new ADR is added.

## 5. Cross-reference updates

After file moves, the following internal links must be updated:

- `docs/README.md` — all directory table links
- `docs/reference/api-spec.md` — add `<swagger-ui>` tag, update any relative links
- Any document referencing `overview/`, `architecture/`, `product/`, `process/`, `migration/` paths

## Out of scope

- Changing content within individual documents (only paths and metadata headers)
- CI/CD pipeline to build and publish the MkDocs site
- Additional ADRs beyond `001-go-to-python.md`
