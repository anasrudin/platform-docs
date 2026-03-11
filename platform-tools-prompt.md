# platform-tools — Coding Agent Implementation Prompt

> Copy this entire prompt into your coding agent (Claude Code, Cursor, Aider, etc.)

---

## CONTEXT

You are implementing **platform-tools** — 67 tool implementations across 3 runtime tiers.

Every tool is a standalone, versioned unit that exposes a gRPC `ExecutionService` server.
**platform-core** orchestrates execution; **platform-tools** only implements tool logic.

```
platform-core  ──gRPC──►  sandbox pod (platform-tools container)
                               └── ExecutionService.Execute(input_json)
                                       └── tool.py:run(input_data) → result
```

Communication protocol: `api/proto/execution.proto` (from platform-core repo).

---

## REPO STRUCTURE

```
platform-tools/
├── Makefile
├── shared/
│   ├── proto/                    # Copy from platform-core/api/proto/
│   │   └── execution.proto
│   ├── runner_base.py            # Base gRPC server class all Tier 2/3 tools extend
│   └── schemas/                  # JSON Schema validation helpers
├── tier1-wasm/
├── tier2-headless/
├── tier3-gui/
├── tool-specs/
└── scripts/
```

---

## TASK 1 — Shared gRPC Base (shared/runner_base.py)

Create `shared/runner_base.py`:

```python
"""
Base class for all Tier 2 and Tier 3 tool runners.
Subclass this and implement `run(input_data: dict) -> dict`.
"""
import json
import logging
import os
import signal
import sys
from concurrent import futures

import grpc

# Proto-generated imports (relative to each tool's src/ dir that symlinks shared/proto)
from proto import execution_pb2, execution_pb2_grpc

logger = logging.getLogger(__name__)


class ToolRunner(execution_pb2_grpc.ExecutionServiceServicer):
    """Extend this class and implement run()."""

    def run(self, input_data: dict) -> dict:
        """Override with your tool logic. Must return a JSON-serialisable dict."""
        raise NotImplementedError

    # ── gRPC handlers ──────────────────────────────────────────────────────
    def Execute(self, request, context):
        job_id = request.job_id
        logger.info(f"execute job={job_id} tool={request.tool_name}")
        try:
            input_data = json.loads(request.input_json)
            result = self.run(input_data)
            return execution_pb2.ExecuteResult(
                job_id=job_id,
                exit_code=0,
                stdout=json.dumps(result),
                duration_ms=0,   # platform-core measures wall time
            )
        except Exception as exc:
            logger.exception(f"tool error job={job_id}")
            return execution_pb2.ExecuteResult(
                job_id=job_id,
                exit_code=1,
                stderr=str(exc),
            )

    def TakeScreenshot(self, request, context):
        """Tier 3 only — override in desktop tools."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        return execution_pb2.ScreenshotResult()

    def SendInput(self, request, context):
        """Tier 3 only — override in desktop tools."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        return execution_pb2.InputAck()

    # ── Server lifecycle ───────────────────────────────────────────────────
    @classmethod
    def serve(cls, port: int = 50051):
        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=4),
            options=[
                ("grpc.max_receive_message_length", 64 * 1024 * 1024),
                ("grpc.max_send_message_length", 64 * 1024 * 1024),
            ],
        )
        execution_pb2_grpc.add_ExecutionServiceServicer_to_server(cls(), server)
        server.add_insecure_port(f"[::]:{port}")
        server.start()
        logger.info(f"tool runner listening on :{port}")

        def _shutdown(sig, frame):
            server.stop(grace=5)
            sys.exit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
        server.wait_for_termination()
```

---

## TASK 2 — Shared Dockerfile base (shared/Dockerfile.base)

```dockerfile
# shared/Dockerfile.base — Tier 2 headless base image
FROM python:3.12-slim

WORKDIR /app

# gRPC + proto tools
RUN pip install --no-cache-dir \
    grpcio==1.64.0 \
    grpcio-tools==1.64.0 \
    protobuf==5.27.2

# Copy shared proto + runner base
COPY shared/ /app/shared/

# Generate Python protobuf code
RUN python -m grpc_tools.protoc \
    -I /app/shared/proto \
    --python_out=/app/shared/proto \
    --grpc_python_out=/app/shared/proto \
    /app/shared/proto/execution.proto

EXPOSE 50051
```

---

## TASK 3 — Tier 2: python_run tool

### `tier2-headless/code/python_run/tool.json`
```json
{
  "name": "python_run",
  "tier": "headless",
  "timeout_ms": 30000,
  "description": "Execute an arbitrary Python script in an isolated container",
  "input_schema": {
    "type": "object",
    "required": ["code"],
    "properties": {
      "code":         { "type": "string", "description": "Python source code to execute" },
      "requirements": { "type": "array",  "items": { "type": "string" }, "description": "pip packages to install" },
      "stdin":        { "type": "string", "description": "Optional stdin input" },
      "timeout_ms":   { "type": "integer", "default": 30000 }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "stdout":      { "type": "string" },
      "stderr":      { "type": "string" },
      "exit_code":   { "type": "integer" },
      "duration_ms": { "type": "integer" }
    }
  }
}
```

### `tier2-headless/code/python_run/src/tool.py`
```python
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(input_data: dict) -> dict:
    code         = input_data["code"]
    requirements = input_data.get("requirements", [])
    stdin_data   = input_data.get("stdin", "")
    timeout_ms   = input_data.get("timeout_ms", 30_000)

    # Install requirements if specified
    if requirements:
        _install_requirements(requirements)

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(code)
        script_path = f.name

    try:
        start = time.monotonic_ns()
        proc = subprocess.run(
            [sys.executable, script_path],
            input=stdin_data.encode(),
            capture_output=True,
            timeout=timeout_ms / 1000,
        )
        duration_ms = (time.monotonic_ns() - start) // 1_000_000
        return {
            "stdout":      proc.stdout.decode(errors="replace"),
            "stderr":      proc.stderr.decode(errors="replace"),
            "exit_code":   proc.returncode,
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timeout exceeded", "exit_code": 124, "duration_ms": timeout_ms}
    finally:
        Path(script_path).unlink(missing_ok=True)


def _install_requirements(packages: list[str]):
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", *packages],
        check=True,
        capture_output=True,
        timeout=120,
    )
```

### `tier2-headless/code/python_run/src/runner.py`
```python
import sys, os
sys.path.insert(0, "/app/shared")

from runner_base import ToolRunner
from tool import run as _run


class PythonRunRunner(ToolRunner):
    def run(self, input_data):
        return _run(input_data)


if __name__ == "__main__":
    PythonRunRunner.serve()
```

### `tier2-headless/code/python_run/Dockerfile`
```dockerfile
FROM gcr.io/platform/tool-runner-base:latest

WORKDIR /app
COPY src/ /app/
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "/app/runner.py"]
```

---

## TASK 4 — Tier 2: image_ocr tool

### `tier2-headless/media/image_ocr/tool.json`
```json
{
  "name": "image_ocr",
  "tier": "headless",
  "timeout_ms": 30000,
  "description": "Extract text from an image using Tesseract OCR",
  "input_schema": {
    "type": "object",
    "required": ["image_base64"],
    "properties": {
      "image_base64": { "type": "string", "description": "Base64-encoded PNG/JPG image" },
      "language":     { "type": "string", "default": "eng", "description": "Tesseract language code" },
      "psm":          { "type": "integer", "default": 3, "description": "Tesseract page segmentation mode" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "text":        { "type": "string" },
      "confidence":  { "type": "number" },
      "blocks":      { "type": "array" }
    }
  }
}
```

### `tier2-headless/media/image_ocr/src/tool.py`
```python
import base64
import io
import pytesseract
from PIL import Image


def run(input_data: dict) -> dict:
    img_b64  = input_data["image_base64"]
    lang     = input_data.get("language", "eng")
    psm      = input_data.get("psm", 3)

    img_bytes = base64.b64decode(img_b64)
    image = Image.open(io.BytesIO(img_bytes))

    config = f"--psm {psm}"
    data = pytesseract.image_to_data(
        image, lang=lang, config=config,
        output_type=pytesseract.Output.DICT,
    )

    words = [
        {"text": t, "confidence": float(c), "left": l, "top": tp, "width": w, "height": h}
        for t, c, l, tp, w, h in zip(
            data["text"], data["conf"], data["left"],
            data["top"], data["width"], data["height"]
        )
        if t.strip() and int(c) > 0
    ]

    full_text = pytesseract.image_to_string(image, lang=lang, config=config)
    avg_conf  = sum(w["confidence"] for w in words) / len(words) if words else 0.0

    return {"text": full_text.strip(), "confidence": avg_conf, "blocks": words}
```

### `tier2-headless/media/image_ocr/requirements.txt`
```
pytesseract==0.3.13
Pillow==10.4.0
```

---

## TASK 5 — Tier 2: sql_query tool

### `tier2-headless/integration/sql_query/src/tool.py`
```python
import psycopg
import json


def run(input_data: dict) -> dict:
    dsn    = input_data["dsn"]         # e.g. "postgresql://user:pass@host:5432/db"
    query  = input_data["query"]
    params = input_data.get("params", [])

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                columns = [desc.name for desc in cur.description]
                rows    = [dict(zip(columns, row)) for row in cur.fetchall()]
                return {"rows": rows, "row_count": len(rows), "columns": columns}
            else:
                conn.commit()
                return {"row_count": cur.rowcount, "rows": [], "columns": []}
```

---

## TASK 6 — Tier 3: screenshot_capture tool

### `tier3-gui/desktop/screenshot_capture/src/tool.py`
```python
import base64
import io
import subprocess
import tempfile
import time
from pathlib import Path


def capture_screenshot(display: str = ":99") -> dict:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    env = {"DISPLAY": display}
    start = time.monotonic_ns()
    subprocess.run(["scrot", path], env={**__import__("os").environ, **env}, check=True, timeout=10)
    latency_ms = (time.monotonic_ns() - start) // 1_000_000

    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)

    from PIL import Image
    img = Image.open(io.BytesIO(data))
    width, height = img.size

    return {
        "png_base64":  base64.b64encode(data).decode(),
        "width":       width,
        "height":      height,
        "latency_ms":  latency_ms,
    }
```

### `tier3-gui/desktop/screenshot_capture/src/runner.py`
```python
import sys
sys.path.insert(0, "/app/shared")

import grpc
from runner_base import ToolRunner
from proto import execution_pb2
from tool import capture_screenshot
import base64


class ScreenshotRunner(ToolRunner):
    def run(self, input_data):
        return capture_screenshot(input_data.get("display", ":99"))

    def TakeScreenshot(self, request, context):
        result = capture_screenshot()
        return execution_pb2.ScreenshotResult(
            png_bytes=base64.b64decode(result["png_base64"]),
            width=result["width"],
            height=result["height"],
            latency_ms=result["latency_ms"],
        )


if __name__ == "__main__":
    ScreenshotRunner.serve()
```

---

## TASK 7 — Tier 3: computer_action tool

### `tier3-gui/desktop/computer_action/src/tool.py`
```python
import subprocess
import time
import os


def send_input(event: dict) -> dict:
    event_type = event["type"]   # click | type | scroll | key | move
    display    = event.get("display", ":99")
    env        = {**os.environ, "DISPLAY": display}

    start = time.monotonic_ns()

    if event_type == "click":
        x, y = event["x"], event["y"]
        button = event.get("button", 1)  # 1=left 2=middle 3=right
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], env=env, check=True)
        subprocess.run(["xdotool", "click", str(button)], env=env, check=True)

    elif event_type == "type":
        text = event["text"]
        subprocess.run(["xdotool", "type", "--clearmodifiers", text], env=env, check=True)

    elif event_type == "key":
        key = event["key"]   # e.g. "Return", "ctrl+c", "super"
        subprocess.run(["xdotool", "key", key], env=env, check=True)

    elif event_type == "scroll":
        x, y = event.get("x", 0), event.get("y", 0)
        direction = event.get("direction", "down")  # up | down
        button = "4" if direction == "up" else "5"
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], env=env, check=True)
        subprocess.run(["xdotool", "click", button], env=env, check=True)

    elif event_type == "move":
        x, y = event["x"], event["y"]
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], env=env, check=True)

    else:
        raise ValueError(f"Unknown event type: {event_type}")

    latency_ms = (time.monotonic_ns() - start) // 1_000_000
    return {"success": True, "latency_ms": latency_ms}
```

---

## TASK 8 — Tier 3: browser_screenshot tool

### `tier3-gui/browser/browser_screenshot/src/tool.py`
```python
import base64
from playwright.sync_api import sync_playwright


def run(input_data: dict) -> dict:
    url        = input_data["url"]
    full_page  = input_data.get("full_page", True)
    width      = input_data.get("viewport_width", 1280)
    height     = input_data.get("viewport_height", 720)
    wait_ms    = input_data.get("wait_ms", 1000)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,           # Uses Xvfb DISPLAY=:99
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(wait_ms)

        png_bytes = page.screenshot(full_page=full_page)
        browser.close()

    return {
        "png_base64": base64.b64encode(png_bytes).decode(),
        "size_bytes": len(png_bytes),
    }
```

---

## TASK 9 — Tool Specs (JSON Schema)

Create `tool-specs/python_run.schema.json` as a reference — mirror the structure of `tool.json` for each tool but add `$schema` and `$id`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://platform.io/tools/python_run/input",
  "title": "python_run input",
  "type": "object",
  "required": ["code"],
  "properties": {
    "code":         { "type": "string" },
    "requirements": { "type": "array", "items": { "type": "string" } },
    "stdin":        { "type": "string" },
    "timeout_ms":   { "type": "integer", "default": 30000 }
  },
  "additionalProperties": false
}
```

Repeat this pattern for all 67 tools. The schema must match the `input_schema` field in each `tool.json`.

---

## TASK 10 — scripts/new-tool.sh

```bash
#!/usr/bin/env bash
# Usage: ./scripts/new-tool.sh --tier tier2-headless --name my_tool

set -euo pipefail
TIER=""
NAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --tier) TIER="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

[[ -z "$TIER" || -z "$NAME" ]] && { echo "Usage: $0 --tier TIER --name NAME"; exit 1; }

DEST="${TIER}/${NAME}"
TEMPLATE="${TIER}/_template"

[[ -d "$DEST" ]] && { echo "Tool $DEST already exists"; exit 1; }
[[ ! -d "$TEMPLATE" ]] && { echo "Template not found: $TEMPLATE"; exit 1; }

cp -r "$TEMPLATE" "$DEST"
sed -i "s/TOOL_NAME_PLACEHOLDER/$NAME/g" "$DEST/tool.json"

echo "✅ Scaffolded $DEST"
echo "   Next: implement $DEST/src/tool.py and update $DEST/tool.json schema"
```

---

## TASK 11 — Makefile

```makefile
.PHONY: build-all test-all publish new-tool

TIER2_TOOLS := $(shell find tier2-headless -name 'Dockerfile' -exec dirname {} \; | sort)
TIER3_TOOLS := $(shell find tier3-gui -name 'Dockerfile.desktop' -exec dirname {} \; | sort)

build-all: build-tier2 build-tier3   ## Build all container images

build-tier2:
	@for dir in $(TIER2_TOOLS); do \
	  name=$$(basename $$dir); \
	  echo "▶ Building $$name"; \
	  docker build -t gcr.io/platform/$$name:latest $$dir; \
	done

build-tier3:
	@for dir in $(TIER3_TOOLS); do \
	  name=$$(basename $$dir); \
	  echo "▶ Building $$name (desktop)"; \
	  docker build -f $$dir/Dockerfile.desktop -t gcr.io/platform/$$name:latest $$dir; \
	done

test-all:   ## Run all tool tests
	@find . -name 'test_*.py' -exec pytest {} +

publish:   ## Push all images to GCR
	@for dir in $(TIER2_TOOLS) $(TIER3_TOOLS); do \
	  name=$$(basename $$dir); \
	  docker push gcr.io/platform/$$name:latest; \
	done

new-tool:  ## Scaffold: make new-tool TIER=tier2-headless NAME=my_tool
	./scripts/new-tool.sh --tier $(TIER) --name $(NAME)
```

---

## ACCEPTANCE CRITERIA

### Tier 1 (WASM) ✅
- [ ] All 29 WASM tools have `tool.json` with valid input/output schema
- [ ] `python_snippet` executes Python via Pyodide sandbox, returns stdout/stderr
- [ ] All data/ tools (json_parser, csv_process, etc.) return structured output
- [ ] All web/ tools use WASI HTTP polyfill, no raw sockets
- [ ] All document tools read/write from `/workspace/input` and `/workspace/output`

### Tier 2 (Headless) ✅
- [ ] All 30 headless tools implement `runner.py` extending `ToolRunner` base
- [ ] `python_run` executes arbitrary Python, captures stdout/stderr, respects timeout
- [ ] `image_ocr` returns text + confidence + block positions
- [ ] `audio_transcribe` returns transcript within 2× audio duration
- [ ] `sql_query` executes SELECT and DML queries, returns rows as JSON
- [ ] `ui_parse` returns structured element tree from screenshot
- [ ] All tools start gRPC server on port 50051 and pass readiness probe

### Tier 3 (GUI) ✅
- [ ] All 8 GUI tools run inside Xvfb DISPLAY=:99
- [ ] `screenshot_capture` returns PNG in <200ms
- [ ] `computer_action` (click/type/scroll/key) ACKs in <50ms via xdotool
- [ ] `browser_screenshot` captures full-page PNG via Playwright + Chromium
- [ ] `browser_pdf` produces valid PDF from URL
- [ ] All desktop tools implement `TakeScreenshot` and `SendInput` gRPC RPCs

### All Tools ✅
- [ ] Every tool has `tool.json` with valid JSON Schema for input/output
- [ ] Every tool has `test/input.json` and at least one pytest test
- [ ] `docker build` succeeds for all Tier 2 + Tier 3 tools
- [ ] `make test-all` passes with 0 failures

---

## IMPLEMENTATION ORDER

```
1. shared/runner_base.py + shared/Dockerfile.base
2. Generate proto bindings: python -m grpc_tools.protoc ...
3. Tier 2 simple tools first: python_run → nodejs_run → bash_run
4. Tier 2 data tools: sql_query → git_clone → git_diff
5. Tier 2 media tools: image_process → image_ocr → audio_transcribe → video_extract
6. Tier 2 AI: ui_parse (OmniParser ONNX model integration)
7. Tier 3 base image: Dockerfile.desktop with Xvfb + XFCE + scrot + xdotool + Playwright
8. Tier 3 tools: screenshot_capture → computer_action → browser_screenshot → browser_pdf
9. Tier 1 WASM tools (no gRPC needed — pure Pyodide Python)
10. tool-specs/ JSON Schema for all 67 tools
11. scripts/ (new-tool.sh, build-all.sh, test-all.sh)
12. CI: .github/workflows/ci.yml
```
