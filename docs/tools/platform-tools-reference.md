# Platform Tools Reference

This is the condensed tool-system view. The authoritative details live in:

- [`memory-bank/tool-registry.md`](../../memory-bank/tool-registry.md)
- [`memory-bank/systemPatterns.md`](../../memory-bank/systemPatterns.md)
- [`memory-bank/techContext.md`](../../memory-bank/techContext.md)
- [`memory-bank/productContext.md`](../../memory-bank/productContext.md)

## Current Tool Model

The control plane selects tools by capability and runtime metadata, not by hard-coded execution paths.

```text
Agent task -> skill resolver -> tool selector -> runtime router -> runtime host agent
```

Every registered tool is expected to carry at least:

- tool name
- runtime tier
- skill/category
- entry point
- timeout and memory budget
- optional snapshot template for Firecracker tools
- health/status used for routing

## Runtime Tiers

The memory bank currently tracks 27 planned tools, not the older speculative 67-tool layout.

| Runtime | Planned tools | Examples |
|---|---|---|
| WASM | 11 | `html_parse`, `json_parse`, `markdown_convert`, `llm_call` |
| Firecracker | 10 | `python_exec`, `bash_run`, `nodejs_run`, `sql_query` |
| GUI | 6 | `browser_open`, `web_scrape`, `screenshot`, `form_automation` |

Tier rules:

- WASM is the fast path for small, mostly stateless work.
- Firecracker is the default secure-compute path for untrusted code.
- GUI is reserved for browser or interactive flows.

## Skill Routing

Current skill-to-tool routing from the memory bank:

| Skill | Primary | Fallback / related |
|---|---|---|
| `coding` | `python_exec` | `nodejs_run`, `bash_run` |
| `scraping` | `html_parse` | `web_scrape`, `browser_open` |
| `document` | `docx_generate` | `xlsx_generate`, `markdown_convert`, `browser_pdf` |
| `data` | `json_parse` | `csv_process`, `xml_parse`, `yaml_parse`, `sql_query` |
| `terminal` | `bash_run` | `file_ops` |
| `media` | `image_process` | `audio_transcribe`, `screenshot` |
| `ai` | `llm_call` | none listed |
| `automation` | `form_automation` | `browser_click` |

## Runtime-Specific Constraints

Patterns that must stay aligned with the memory bank:

- business logic stays in the control plane; schedulers only place work
- warm pools are first-class for WASM, Firecracker, and GUI runtimes
- filesystem state is per-sandbox and disposable
- WASM should stay offline or tightly restricted by default
- execution output must be recorded as immutable artifacts

Infrastructure assumptions that affect tool design:

- Go-based control plane with Nomad scheduling
- PostgreSQL for session/execution metadata
- Redis or NATS for queues and coordination
- MinIO for artifacts, snapshots, and module storage
- TAP networking plus iptables/tc for Firecracker isolation

## Snapshot Templates

Current Firecracker templates tracked in the memory bank:

| Template | Installed runtime |
|---|---|
| `python-v1` | Python 3.12 + pip + data libraries |
| `node-v1` | Node.js 20 + npm |
| `bash-v1` | Bash + coreutils + curl |
| `whisper-v1` | Python 3.12 + whisper.cpp |

## What Changed

Older tool docs described a much larger and more speculative tree. This reference intentionally follows the current memory bank instead:

- fewer planned tools
- registry-first rather than folder-tree-first documentation
- runtime and skill metadata as the main abstraction
