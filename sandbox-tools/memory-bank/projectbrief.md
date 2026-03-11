# Project Brief — sandbox-tools

## One Sentence
`sandbox-tools` is the **tool library** for sandbox-platform: every tool the AI agent can invoke lives here as a self-contained directory with a manifest, an entrypoint, and nothing else.

## Relationship to sandbox-platform
```
sandbox-platform  ←  reads manifest.json  ←  sandbox-tools
                       routes to runtime
                       executes entrypoint
```
The platform owns execution. The tools own business logic. They never import each other's code.

## Directory Layout

```
sandbox-tools/
│
├── wasm/           ← WASM-tier tools  (Go → wasip1, ~10ms)
│   ├── html_parse/
│   ├── json_parse/
│   ├── markdown_convert/
│   └── docx_generate/
│
├── headless/       ← MicroVM-tier tools  (Python/Shell, Firecracker, <80ms cold)
│   ├── python_run/
│   ├── bash_run/
│   ├── git_clone/
│   └── file_ops/
│
└── gui/            ← GUI-tier tools  (Docker+Xvfb, Playwright/LibreOffice)
    ├── browser_open/
    ├── web_scrape/
    ├── excel_edit/
    └── office_automation/
```

## Non-Negotiable Rules
1. Every tool directory **must** contain `manifest.json` — platform won't register it without one.
2. Tools communicate with the platform **only** via `TOOL_INPUT` env var (input) and `stdout` (output) — both are JSON.
3. Tools **must never** write non-JSON to stdout.
4. Tools **must never** access paths outside `/work/` (sandbox-tools cannot enforce this at compile time, but the platform's rootfs does).
5. WASM tools compile with `GOOS=wasip1 GOARCH=wasm` — not `js && wasm`.
