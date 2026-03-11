# Active Context — sandbox-tools

_Update at the start and end of every work session._

## Currently Working On
> Just completed: v1.0 — all 12 tool starters + memory bank

**Next task**:
1. Write `markdown_convert/main.go` (wasip1, stdlib only)
2. Write `docx_generate/main.go` (investigate wasip1-compatible library)
3. Fix `bash_run/run.sh` — shell quoting around `$STDOUT` breaks if output contains quotes

---

## Architecture Decisions (do not change without discussion)

| Decision | Reason |
|----------|--------|
| `TOOL_INPUT` env var for all tiers | Universal — works for Go, Python, Shell, Rust, any language |
| WASM uses `os.Args[1]` not env var | Wasmtime CLI does not inject env vars the same way; args are safer |
| `out()` helper prints JSON | Prevents accidentally mixing debug prints with output |
| `safe_path()` in every file-accessing tool | Platform rootfs can't prevent traversal; tool must self-enforce |
| `browser.close()` in `finally` block | Playwright leaks processes if not closed; container pool would fill with zombie Chrome |
| LibreOffice `--norestore` flag | Without this, LO shows a recovery dialog on startup and hangs |
| Limit web_scrape to 50 elements | Prevent unbounded output that could fill Redis |

---

## Active Known Issues

### Issue 1 — `bash_run` output capture is fragile
**File**: `headless/bash_run/run.sh`
**Problem**: `STDOUT=$(cat "$STDOUT_FILE")` and then using `'''$STDOUT'''` in a Python one-liner breaks if stdout contains single quotes or backslashes.
**Fix**: Replace with a pure Python script (`bash_run.py`) that calls `subprocess.run(["bash", tmpfile])` directly — same pattern as `python_run`.

### Issue 2 — `markdown_convert` and `docx_generate` have no implementation
**Files**: `wasm/markdown_convert/`, `wasm/docx_generate/`
**Problem**: Only `manifest.json` exists.
**Fix for markdown_convert**: Implement using `regexp` + `strings.Replacer` in Go — no external library needed for basic MD→HTML.
**Fix for docx_generate**: The `go-docx` library (github.com/fumiama/go-docx) compiles to wasip1. Add to go.mod and implement.

### Issue 3 — WASM build tag is wrong
**Files**: `wasm/html_parse/main.go`, `wasm/json_parse/main.go`
**Problem**: Build tag says `//go:build js && wasm` — that's for browser WASM.
**Fix**: Change to `//go:build wasip1`

### Issue 4 — `git_clone` entrypoint mismatch
**File**: `headless/git_clone/manifest.json` says `"entrypoint": "clone.sh"` but the file is `clone.py`
**Fix**: Update manifest to `"entrypoint": "clone.py"`

---

## Context for Next Session

1. **Fix Issue 4 first** — it's a one-line manifest fix, blocks platform routing.
2. **Fix Issue 3** — WASM tools will fail to compile with wrong build tag.
3. **Fix Issue 1** — `bash_run` will silently produce wrong JSON for any script with quotes in output.
4. After fixes: run all tools locally with `TOOL_INPUT='...'` before testing on platform.
