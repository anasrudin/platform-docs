# Progress — sandbox-tools

## Status Per Tool

### WASM Tier

| Tool | manifest.json | Entrypoint | Tested | Notes |
|------|:---:|:---:|:---:|-------|
| `html_parse` | ✅ | ✅ `main.go` | ❌ | Extracts title, text, links — no CGO, stdlib only |
| `json_parse` | ✅ | ✅ `main.go` | ❌ | Dot-notation path query |
| `markdown_convert` | ✅ | ❌ missing | ❌ | **Needs `main.go`** — convert MD → HTML |
| `docx_generate` | ✅ | ❌ missing | ❌ | **Needs `main.go`** — needs docx library for wasip1 |

### MicroVM / Headless Tier

| Tool | manifest.json | Entrypoint | Tested | Notes |
|------|:---:|:---:|:---:|-------|
| `python_run` | ✅ | ✅ `main.py` | ❌ | Runs arbitrary Python, captures stdout/stderr |
| `bash_run` | ✅ | ✅ `run.sh` | ❌ | Runs bash script, wraps output as JSON |
| `git_clone` | ✅ | ✅ `clone.py` | ❌ | Clones repo to `/work/`, returns file list |
| `file_ops` | ✅ | ✅ `file_ops.py` | ❌ | read/write/list/delete within `/work/` |

### GUI Tier

| Tool | manifest.json | Entrypoint | Tested | Notes |
|------|:---:|:---:|:---:|-------|
| `browser_open` | ✅ | ✅ `browser.py` | ❌ | Opens URL, returns title + base64 screenshot |
| `web_scrape` | ✅ | ✅ `scrape.py` | ❌ | CSS selector scrape → text/html/links |
| `excel_edit` | ✅ | ✅ `excel.py` | ❌ | read/write cells via openpyxl |
| `office_automation` | ✅ | ✅ `office.py` | ❌ | convert via LibreOffice headless (merge=TODO) |

---

## What Is Missing ❌

### Priority 1 — Needed for end-to-end test

- [ ] `wasm/markdown_convert/main.go` — implement MD→HTML (no CGO, use regexp/strings)
- [ ] `wasm/docx_generate/main.go` — needs a wasip1-compatible docx library (tricky)
- [ ] Unit tests for all 12 tools (run locally before deploying)
- [ ] WASM build: `GOOS=wasip1 GOARCH=wasm go build -o html_parse.wasm ./wasm/html_parse/`

### Priority 2 — Polish

- [ ] `office_automation`: implement `merge` operation
- [ ] `bash_run`: rewrite output capture in pure Python to avoid quoting issues
- [ ] `git_clone`: support SSH clone (needs key injection via env)
- [ ] `web_scrape`: add pagination support (`max_pages` input field)
- [ ] `browser_open`: add `click`, `fill`, `wait_for_selector` actions

### Priority 3 — New tools (future)

- [ ] `pdf_read` (wasm) — extract text from PDF via pure-Go library
- [ ] `csv_parse` (wasm) — parse CSV, return 2D array + headers
- [ ] `http_request` (microvm) — make HTTP GET/POST, return response
- [ ] `zip_extract` (microvm) — unzip archive to `/work/`
- [ ] `screenshot` (gui) — full-page screenshot of a URL
- [ ] `form_fill` (gui) — fill and submit HTML forms via Playwright

---

## How to Test a Tool Locally

```bash
# Python tool
TOOL_INPUT='{"code": "print(1+1)"}' python3 headless/python_run/main.py

# Shell tool
TOOL_INPUT='{"script": "echo hello"}' bash headless/bash_run/run.sh

# WASM tool (after building)
wasmtime wasm-modules/html_parse.wasm -- '{"html": "<h1>hi</h1>"}'
```

Expected: one line of valid JSON on stdout, `exit_code` field present.

---

## Changelog

| Version | Changes |
|---------|---------|
| v1.0 | 12 tool starters — manifests, entrypoints for all tiers |
| v1.0 | WASM: html_parse + json_parse Go source |
| v1.0 | Headless: python_run, bash_run, git_clone, file_ops |
| v1.0 | GUI: browser_open (Playwright), web_scrape, excel_edit, office_automation |
| v1.0 | Memory bank created |
