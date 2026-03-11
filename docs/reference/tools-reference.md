# Platform Tools Reference

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, platform engineers, reviewers |
| Scope | Current tool model, routing rules, runtime fit, and operational constraints |
| Last updated | March 11, 2026 |

## Executive summary

The platform uses a registry-first tool model. Tools are selected by capability, runtime metadata, and policy rather than by hard-coded execution paths. Runtime routing is therefore a control-plane concern, while each runtime host agent focuses on isolated execution.

## Tool selection model

```text
Agent task -> skill resolver -> tool selector -> runtime router -> runtime host agent
```

### Design principles

- Tool selection is metadata-driven.
- Runtime choice is explicit and policy-aware.
- Schedulers place work; they do not own tool logic.
- Execution outputs must be persisted outside the sandbox lifecycle.

## Tool registration contract

Each registered tool is expected to carry at least the following metadata:

| Field | Purpose |
|---|---|
| Tool name | Stable identifier used for selection and execution |
| Runtime tier | Determines the execution environment |
| Skill or category | Supports higher-level routing and discovery |
| Entry point | Defines how the runtime host agent launches the tool |
| Timeout and memory budget | Supports scheduling and enforcement |
| Snapshot template | Optional Firecracker base image or snapshot reference |
| Health state | Allows safe routing and operational visibility |

## Runtime portfolio

The current planning model tracks 27 tools, replacing an older and more speculative 67-tool design.

| Runtime | Planned tools | Example tools | Primary fit |
|---|---|---|---|
| WASM | 11 | `html_parse`, `json_parse`, `markdown_convert`, `llm_call` | Fast, mostly stateless work |
| Firecracker | 10 | `python_exec`, `bash_run`, `nodejs_run`, `sql_query` | Secure compute for untrusted execution |
| GUI | 6 | `browser_open`, `web_scrape`, `screenshot`, `form_automation` | Browser and interaction-driven flows |

### Runtime usage rules

- WASM is the preferred path for small and tightly bounded execution.
- Firecracker is the default secure-compute path for untrusted code.
- GUI is reserved for browser-driven or interactive flows.

## Current skill routing

| Skill | Primary tool | Fallback or related tools |
|---|---|---|
| `coding` | `python_exec` | `nodejs_run`, `bash_run` |
| `scraping` | `html_parse` | `web_scrape`, `browser_open` |
| `document` | `docx_generate` | `xlsx_generate`, `markdown_convert`, `browser_pdf` |
| `data` | `json_parse` | `csv_process`, `xml_parse`, `yaml_parse`, `sql_query` |
| `terminal` | `bash_run` | `file_ops` |
| `media` | `image_process` | `audio_transcribe`, `screenshot` |
| `ai` | `llm_call` | None currently defined |
| `automation` | `form_automation` | `browser_click` |

## Operational constraints

The following constraints are part of the current platform model:

- business logic remains in the control plane
- warm pools are first-class for WASM, Firecracker, and GUI
- filesystem state is sandbox-local and disposable
- WASM should remain offline or tightly restricted by default
- execution output must be recorded as immutable artifacts

### Infrastructure assumptions

- Go-based control plane with Nomad scheduling
- PostgreSQL for session and execution metadata
- Redis or NATS for queues and coordination
- MinIO for artifacts, snapshots, and module storage
- TAP networking plus iptables and `tc` for Firecracker isolation

## Firecracker snapshot templates

| Template | Installed runtime |
|---|---|
| `python-v1` | Python 3.12 with `pip` and data libraries |
| `node-v1` | Node.js 20 with `npm` |
| `bash-v1` | Bash, coreutils, and `curl` |
| `whisper-v1` | Python 3.12 with `whisper.cpp` |

## Evolution from the earlier model

Compared with earlier internal tooling drafts, the current model is intentionally narrower and more operationally realistic:

- fewer planned tools
- registry-first instead of folder-tree-first documentation
- runtime and skill metadata as the core abstraction
- stronger separation between control-plane logic and runtime execution

## Internal source materials

Detailed planning inputs remain available in internal project files, including `tool-registry`, `systemPatterns`, `techContext`, and `productContext`.
