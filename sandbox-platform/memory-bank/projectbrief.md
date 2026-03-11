# Project Brief

## One Sentence
sandbox-platform is an **agent execution engine** that lets AI agents run tools (code, shell, browser automation) inside isolated runtimes safely and at low latency.

## Problem Solved
AI agents need to execute arbitrary code — Python, shell, browser automation — without security risk. This platform provides three isolated runtime tiers with a warm pool so latency stays low.

## Two Binaries
| Binary | Port | Function |
|--------|------|----------|
| `cmd/api-server` | `:8080` | Accept HTTP requests, JWT auth, rate limit, enqueue jobs |
| `cmd/node-agent` | — | Dequeue jobs, dispatch to runtime, report results |

## Three Runtime Tiers
| Tier | Runtime | Use Case | Target Latency |
|------|---------|----------|----------------|
| `wasm` | Wasmtime CLI | Pure computation, no I/O | < 20ms |
| `microvm` | Firecracker | Code with I/O, network, subprocess | < 80ms (snapshot) |
| `gui` | Docker + Xvfb | Browser, office tools, screen | < 2s |

## Two Repos
- `sandbox-platform` — this repo (control plane + node agent + runtimes)
- `sandbox-tools` — tool implementations (WASM binaries, Python scripts)

## 12 Starter Tools
| Tier | Tools |
|------|-------|
| wasm | html_parse, json_parse, markdown_convert, docx_generate |
| microvm | python_run, bash_run, git_clone, file_ops |
| gui | browser_open, web_scrape, excel_edit, office_automation |
