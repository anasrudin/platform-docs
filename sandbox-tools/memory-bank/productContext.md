# Product Context — sandbox-tools

## What Each Tier Is For

### WASM (`wasm/`)
Pure computation with no external I/O. The platform loads the `.wasm` binary via Wasmtime and passes `TOOL_INPUT` as a CLI argument (not an env var — Wasmtime CLI passes args directly). Response must be printed to stdout as a single JSON line.

**When to add a tool here**: the work is purely transformational — parse, convert, extract, validate. No network, no subprocess, no filesystem writes.

Target latency: **< 20ms** (module cached after first load).

### MicroVM / Headless (`headless/`)
Code that needs the real OS: subprocess, pip install, git, file I/O. Runs inside a Firecracker microVM booted from a snapshot. The snapshot already has Python 3, pip, git, curl, and common packages installed.

Input arrives via `TOOL_INPUT` environment variable. Output is printed to stdout as a single JSON line.

**When to add a tool here**: anything that runs a process, reads/writes files in `/work/`, or calls the network.

Target latency: **< 80ms** from snapshot resume.

### GUI (`gui/`)
Requires a visible display. Runs in a Docker container with Xvfb (virtual framebuffer) on `DISPLAY=:99`. Chromium, Playwright, LibreOffice, and Python are all pre-installed in the `sandbox/desktop-runner` image.

Input via `TOOL_INPUT`, output via stdout JSON.

**When to add a tool here**: needs to render a browser, interact with a GUI app, take screenshots, or use LibreOffice.

Target latency: **< 2s** (container pre-warmed in pool).

## User-Visible Behaviour
The AI agent sees only:
- `tool` name (e.g. `"python_run"`)
- `input` JSON object (e.g. `{"code": "print(1+1)"}`)
- `output` — whatever the tool prints to stdout

The agent has no visibility into which tier runs. Tier selection is automatic based on the manifest.

## Sandbox Contract
All tools run with:
- No network access (except `git_clone` and `web_scrape` which require network)
- Filesystem access limited to `/work/`
- CPU: 2 vCPUs max
- Memory: 512 MiB max (MicroVM), 256 MiB (WASM), 1 GiB (GUI)
- Timeout: as specified in `manifest.json`
