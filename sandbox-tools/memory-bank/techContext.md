# Tech Context — sandbox-tools

## Manifest Schema

Every tool directory must have a `manifest.json`:

```json
{
  "name":        "tool_name",
  "tier":        "wasm | microvm | gui",
  "entrypoint":  "main.py",
  "timeout":     60,
  "description": "One-line description of what the tool does.",
  "env": {
    "OPTIONAL_KEY": "optional_value"
  }
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | ✅ | Must match directory name exactly |
| `tier` | ✅ | `wasm`, `microvm`, or `gui` |
| `entrypoint` | ✅ | Filename within the tool directory |
| `timeout` | ✅ | Seconds. Hard limit enforced by platform |
| `description` | optional | Shown in GET /v1/tools |
| `env` | optional | Extra env vars injected at runtime |

## Tool I/O Protocol

```
Input:   TOOL_INPUT environment variable = JSON string
Output:  stdout = one JSON line, must include "exit_code" field
Errors:  stderr (captured, stored in job result, not returned to agent)
```

### Minimal valid output:
```json
{"exit_code": 0}
```

### Recommended output pattern (Python):
```python
import json, os

inp = json.loads(os.environ.get("TOOL_INPUT", "{}"))
# ... do work ...
print(json.dumps({"result": result, "exit_code": 0}))
```

**WASM exception**: Wasmtime CLI passes input as `argv[1]`, not env var:
```go
// main.go
func main() {
    inp := os.Args[1]   // JSON string
    // ... do work ...
    fmt.Println(string(output))  // one JSON line
}
```

## WASM Build

```bash
# Compile any tool in wasm/
GOOS=wasip1 GOARCH=wasm go build -o {tool_name}.wasm .

# Place output at:
/var/sandbox/wasm-modules/{tool_name}.wasm
```

Build tag required at top of every WASM main.go:
```go
//go:build wasip1
```

> ⚠️ Do NOT use `//go:build js && wasm` — that's for browser WASM, not Wasmtime.

## Python Environment (MicroVM and GUI)

The Firecracker rootfs and the Docker desktop-runner image both have:

| Package | Version |
|---------|---------|
| Python | 3.11 |
| pip | latest |
| playwright | 1.44.0 |
| selenium | 4.21.0 |
| beautifulsoup4 | 4.12.3 |
| requests | 2.32.3 |
| openpyxl | 1.3.1 |
| python-docx | 1.1.2 |
| Pillow | 10.4.0 |
| lxml | 5.2.2 |

If a headless tool needs an extra pip package:
1. Add it to the rootfs snapshot build script (preferred, zero cold-start cost)
2. Or `subprocess.run(["pip", "install", pkg])` inside the tool (adds ~2s per install)

## Shell Tools (`headless/`)

Shell scripts receive input via `TOOL_INPUT` env var. Extract with Python one-liner:
```bash
VALUE=$(python3 -c "import json,os; print(json.loads(os.environ['TOOL_INPUT']).get('key',''))")
```

Output must be valid JSON printed to stdout:
```bash
python3 -c "import json; print(json.dumps({'result': '$VALUE', 'exit_code': 0}))"
```

## GUI Runtime Details

- Display: `DISPLAY=:99` (Xvfb, 1920×1080×24)
- Chromium binary: `/usr/bin/chromium-browser`
- Playwright launch args always needed: `--no-sandbox --disable-dev-shm-usage`
- LibreOffice: `libreoffice --headless --norestore`

## Filesystem in Sandbox

```
/work/      ← tool read/write area (persists for job duration only)
/tool/      ← tool entrypoints (read-only, mounted by platform)
/tmp/       ← temporary files
```

All paths outside these three are read-only or inaccessible.

## Adding a New Tool — Checklist

```
[ ] Create directory:   sandbox-tools/{tier}/{tool_name}/
[ ] Write manifest:     manifest.json (all required fields)
[ ] Write entrypoint:   main.py / run.sh / main.go
[ ] Test locally:       TOOL_INPUT='{"key":"val"}' python3 main.py
[ ] Verify output:      stdout is valid JSON with exit_code field
[ ] Register in platform: add to internal/tool/registry/registry.go builtinTools()
[ ] Add routing rule:   add to internal/router/rules.go defaultRules()
[ ] Build WASM (if applicable): GOOS=wasip1 GOARCH=wasm go build -o {name}.wasm .
```
