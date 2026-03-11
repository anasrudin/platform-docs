# System Patterns — sandbox-tools

## Tool Lifecycle (end-to-end)

```
Agent sends:  {"tool": "python_run", "input": {"code": "print(1+1)"}}
                │
                ▼
Platform reads manifest.json  →  tier = "microvm"
                │
                ▼
Platform routes to Firecracker runtime
                │
                ▼
VM boots from snapshot (~80ms)
                │
                ▼
Platform sets: TOOL_INPUT = '{"code":"print(1+1)"}'
Platform exec: python3 /tool/python_run/main.py
                │
                ▼
Tool reads TOOL_INPUT, executes code, prints result to stdout:
  {"stdout": "2\n", "stderr": "", "exit_code": 0}
                │
                ▼
Platform captures stdout  →  stores in Redis  →  agent polls and gets result
```

## Standard Tool Template (Python)

```python
#!/usr/bin/env python3
"""
{tool_name} — one-line description.
Input:  {"field": "value", ...}
Output: {"result": ..., "exit_code": 0}
"""
import json
import os
import sys


def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        out({"error": f"invalid input JSON: {e}", "exit_code": 1})
        return

    # --- validate required fields ---
    value = inp.get("field")
    if not value:
        out({"error": "field is required", "exit_code": 1})
        return

    # --- do work ---
    try:
        result = do_work(value)
        out({"result": result, "exit_code": 0})
    except Exception as e:
        out({"error": str(e), "exit_code": 1})


def do_work(value):
    return value  # replace with real logic


def out(d: dict):
    """Always use this. Never print raw strings to stdout."""
    print(json.dumps(d))


if __name__ == "__main__":
    main()
```

## Standard Tool Template (WASM / Go)

```go
//go:build wasip1

package main

import (
    "encoding/json"
    "fmt"
    "os"
)

type Input struct {
    Field string `json:"field"`
}

type Output struct {
    Result any    `json:"result,omitempty"`
    Error  string `json:"error,omitempty"`
}

func main() {
    if len(os.Args) < 2 {
        writeOut(Output{Error: "TOOL_INPUT argument required"})
        return
    }
    var inp Input
    if err := json.Unmarshal([]byte(os.Args[1]), &inp); err != nil {
        writeOut(Output{Error: "invalid input: " + err.Error()})
        return
    }
    if inp.Field == "" {
        writeOut(Output{Error: "field is required"})
        return
    }
    writeOut(Output{Result: inp.Field}) // replace with real logic
}

func writeOut(o Output) {
    data, _ := json.Marshal(o)
    fmt.Println(string(data))
}
```

## Path Safety Pattern (file-accessing tools)

Any tool that reads or writes user-provided paths **must** validate them:

```python
WORK_DIR = "/work"

def safe_path(user_path: str) -> str:
    abs_p = os.path.realpath(os.path.join(WORK_DIR, user_path.lstrip("/")))
    if not abs_p.startswith(WORK_DIR):
        raise ValueError(f"path traversal attempt: {user_path!r}")
    return abs_p
```

Never skip this check, even if the path looks safe.

## Error Handling Pattern

| Situation | Correct behaviour |
|-----------|------------------|
| Invalid JSON in TOOL_INPUT | `{"error": "invalid input JSON: ...", "exit_code": 1}` |
| Required field missing | `{"error": "X is required", "exit_code": 1}` |
| Path traversal attempt | `{"error": "path traversal", "exit_code": 1}` |
| Subprocess fails | Include `stdout`, `stderr`, and actual `exit_code` from subprocess |
| Unexpected exception | `{"error": str(e), "exit_code": 1}` — never crash silently |
| Success | `{"result": ..., "exit_code": 0}` |

## Playwright Pattern (GUI tools)

```python
import os
from playwright.sync_api import sync_playwright

os.environ.setdefault("DISPLAY", ":99")

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path="/usr/bin/chromium-browser",
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # ... do work ...
    finally:
        browser.close()  # always close, even on error
```

## What Tools Must Never Do

| Forbidden | Why |
|-----------|-----|
| Write to stdout before the final JSON line | Platform reads only stdout; partial output breaks parsing |
| Import from other tool directories | Tools are isolated; no shared Python packages between tools |
| Access `/etc`, `/var`, `/home` | Outside sandbox boundary |
| `sys.exit()` without printing output first | Agent gets empty result, no error message |
| `print("debug info")` to stdout | Breaks JSON parsing; use `sys.stderr.write()` for debug |
| Sleep for > timeout value | Platform will kill the process; waste of VM slot |
