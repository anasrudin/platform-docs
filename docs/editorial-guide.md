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
uv pip install -r requirements-docs.txt
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
