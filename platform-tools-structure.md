# platform-tools — Folder Tree & Architecture

> **67 tool implementations across 3 runtime tiers**
> Tier 1 WASM (29) · Tier 2 Headless (30) · Tier 3 GUI (8)

---

## Tier Overview

| Tier | Isolation | Runtime | Cold Start | Tools |
|---|---|---|---|---|
| **1 — WASM** | In-process sandbox | Wasmtime 22 / Pyodide 0.26 | <5ms | 29 |
| **2 — Headless** | Container | python:3.12-slim / node:20-slim | ~300ms warm | 30 |
| **3 — GUI Desktop** | Firecracker VM | Ubuntu 22.04 + Xvfb + XFCE 4.18 | 125ms (snapshot) | 8 |

---

## Folder Tree

```
platform-tools/
├── Makefile                                   # build-all · test-all · publish · new-tool
├── .github/
│   └── workflows/
│       └── ci.yml                             # lint → unit-test → build → push images
│
# ══════════════════════════════════════════════════════════
#  TIER 1 — WASM (29 tools, Wasmtime 22 / Pyodide 0.26)
# ══════════════════════════════════════════════════════════
├── tier1-wasm/
│   │
│   ├── _template/                             # Copy to create a new WASM tool
│   │   ├── tool.json                          # Tool manifest (name, input/output schema)
│   │   ├── src/main.py                        # Pyodide entry or AssemblyScript source
│   │   ├── build.sh                           # → .wasm output
│   │   └── test/input.json
│   │
│   ├── code/
│   │   ├── python_snippet/                    # Run an isolated Python snippet via Pyodide
│   │   │   ├── tool.json
│   │   │   ├── src/main.py
│   │   │   └── test/
│   │   └── nodejs_snippet/                    # Run JS snippet via QuickJS WASM
│   │       ├── tool.json
│   │       ├── src/main.js
│   │       └── test/
│   │
│   ├── data/
│   │   ├── json_parser/                       # Parse + transform JSON (jq-like)
│   │   ├── csv_process/                       # Filter / aggregate CSV rows
│   │   ├── xml_parse/                         # XPath extraction from XML
│   │   ├── text_process/                      # Regex replace, split, trim, template
│   │   └── yaml_parse/                        # YAML → JSON roundtrip
│   │
│   ├── web/
│   │   ├── web_fetch/                         # HTTP GET via WASI HTTP polyfill
│   │   ├── web_search/                        # Search API wrapper (Brave/Serper)
│   │   ├── rss_fetch/                         # Parse RSS/Atom feed
│   │   ├── html_extract/                      # CSS selector extraction from HTML
│   │   ├── html_to_markdown/                  # Convert HTML → Markdown
│   │   └── markdown_render/                   # Markdown → HTML
│   │
│   ├── documents/
│   │   ├── docx_generate/                     # Template → .docx (python-docx in Pyodide)
│   │   ├── docx_edit/                         # Find-replace in .docx
│   │   ├── docx_parse/                        # Extract text + tables from .docx
│   │   ├── pptx_generate/                     # Template → .pptx
│   │   ├── pptx_edit/                         # Edit slides in existing .pptx
│   │   ├── pptx_parse/                        # Extract text + notes from .pptx
│   │   ├── xlsx_generate/                     # Template → .xlsx (openpyxl in Pyodide)
│   │   ├── xlsx_edit/                         # Edit cells in .xlsx
│   │   ├── xlsx_parse/                        # Extract sheets + rows from .xlsx
│   │   └── pdf_extract/                       # Extract text from PDF (pdfminer.six)
│   │
│   ├── ai/
│   │   ├── llm_call/                          # Call LLM via HTTP (OpenAI/Anthropic/etc.)
│   │   ├── llm_embed/                         # Generate text embeddings
│   │   ├── image_generate/                    # Call image generation API
│   │   ├── embedding_search/                  # cosine similarity search in-memory
│   │   └── code_review/                       # Static analysis + LLM review
│   │
│   ├── code_quality/
│   │   ├── code_lint/                         # Run Ruff / ESLint WASM port
│   │   └── code_format/                       # Run Black / Prettier WASM port
│   │
│   └── integration/
│       ├── file_read/                         # Read file from workspace volume
│       ├── file_write/                        # Write file to workspace volume
│       ├── http_request/                      # Generic HTTP client (GET/POST/PUT/DELETE)
│       ├── email_send/                        # Send email via SMTP API
│       ├── slack_post/                        # Post message to Slack channel
│       ├── slack_search/                      # Search Slack messages
│       ├── webhook_call/                      # Call arbitrary webhook URL
│       └── calendar_create/                   # Create Google Calendar event
│
# ══════════════════════════════════════════════════════════
#  TIER 2 — HEADLESS (30 tools, container-based)
# ══════════════════════════════════════════════════════════
├── tier2-headless/
│   │
│   ├── _template/                             # Copy to create a new headless tool
│   │   ├── tool.json
│   │   ├── Dockerfile                         # FROM python:3.12-slim or node:20-slim
│   │   ├── src/runner.py                      # gRPC server implementing ExecutionService
│   │   ├── requirements.txt
│   │   └── test/
│   │
│   ├── code/
│   │   ├── python_run/                        # Run arbitrary Python script (subprocess)
│   │   │   ├── tool.json
│   │   │   ├── Dockerfile                     # python:3.12-slim + grpc server
│   │   │   ├── src/
│   │   │   │   ├── runner.py                  # gRPC ExecutionService impl
│   │   │   │   └── sandbox.py                 # subprocess isolation helpers
│   │   │   ├── requirements.txt
│   │   │   └── test/
│   │   ├── nodejs_run/                        # Run Node.js script (node:20-slim)
│   │   ├── bash_run/                          # Run bash script with timeout
│   │   ├── deno_run/                          # Run Deno 1.44 script (--allow-net etc.)
│   │   └── r_run/                             # Run R 4.4 script
│   │
│   ├── repo/
│   │   ├── git_clone/                         # git clone shallow + sparse checkout
│   │   ├── git_diff/                          # git diff between refs → structured output
│   │   ├── code_test/                         # Run pytest / jest / go test
│   │   └── code_build/                        # docker build / go build / npm build
│   │
│   ├── media/
│   │   ├── image_process/                     # Resize/crop/convert (Pillow 10 + Sharp 0.33)
│   │   ├── image_ocr/                         # Extract text from image (Tesseract 5.3)
│   │   ├── audio_transcribe/                  # Audio → text (Whisper.cpp)
│   │   └── video_extract/                     # Extract frames/audio (FFmpeg 7.0)
│   │
│   ├── documents/
│   │   └── pdf_render/                        # HTML/URL → PDF (headless Chromium)
│   │
│   ├── ai/
│   │   └── ui_parse/                          # Screenshot → structured UI tree (OmniParser v2)
│   │
│   └── integration/
│       └── sql_query/                         # Execute SQL (psycopg3 / pymongo / etc.)
│
# ══════════════════════════════════════════════════════════
#  TIER 3 — GUI DESKTOP (8 tools, Firecracker VM)
# ══════════════════════════════════════════════════════════
├── tier3-gui/
│   │
│   ├── _template/                             # Copy to create a new GUI tool
│   │   ├── tool.json
│   │   ├── Dockerfile.desktop                 # Ubuntu 22.04 + Xvfb + XFCE + grpc server
│   │   ├── src/runner.py
│   │   └── test/
│   │
│   ├── desktop/
│   │   ├── screenshot_capture/                # Capture full-screen PNG (scrot 1.10)
│   │   │   ├── tool.json
│   │   │   ├── Dockerfile.desktop
│   │   │   ├── src/
│   │   │   │   ├── runner.py                  # gRPC TakeScreenshot impl
│   │   │   │   └── capture.py                 # scrot wrapper
│   │   │   └── test/
│   │   ├── computer_action/                   # Click/type/scroll/key (xdotool 3.20)
│   │   └── desktop_run/                       # Run arbitrary desktop application
│   │
│   └── browser/
│       ├── browser_run/                       # Run Playwright script (Playwright 1.45)
│       ├── browser_screenshot/                # Full-page screenshot (Chromium 126)
│       ├── browser_pdf/                       # Full-page → PDF (Chromium print-to-pdf)
│       ├── browser_click/                     # Click element by selector
│       └── browser_type/                      # Type text into element by selector
│
# ══════════════════════════════════════════════════════════
#  TOOL SPECS (JSON Schema)
# ══════════════════════════════════════════════════════════
├── tool-specs/
│   ├── python_snippet.schema.json
│   ├── nodejs_snippet.schema.json
│   ├── json_parser.schema.json
│   ├── csv_process.schema.json
│   ├── xml_parse.schema.json
│   ├── text_process.schema.json
│   ├── yaml_parse.schema.json
│   ├── web_fetch.schema.json
│   ├── web_search.schema.json
│   ├── rss_fetch.schema.json
│   ├── html_extract.schema.json
│   ├── html_to_markdown.schema.json
│   ├── markdown_render.schema.json
│   ├── docx_generate.schema.json
│   ├── docx_edit.schema.json
│   ├── docx_parse.schema.json
│   ├── pptx_generate.schema.json
│   ├── pptx_edit.schema.json
│   ├── pptx_parse.schema.json
│   ├── xlsx_generate.schema.json
│   ├── xlsx_edit.schema.json
│   ├── xlsx_parse.schema.json
│   ├── pdf_extract.schema.json
│   ├── llm_call.schema.json
│   ├── llm_embed.schema.json
│   ├── image_generate.schema.json
│   ├── embedding_search.schema.json
│   ├── code_review.schema.json
│   ├── code_lint.schema.json
│   ├── code_format.schema.json
│   ├── file_read.schema.json
│   ├── file_write.schema.json
│   ├── http_request.schema.json
│   ├── email_send.schema.json
│   ├── slack_post.schema.json
│   ├── slack_search.schema.json
│   ├── webhook_call.schema.json
│   ├── calendar_create.schema.json
│   ├── python_run.schema.json
│   ├── nodejs_run.schema.json
│   ├── bash_run.schema.json
│   ├── deno_run.schema.json
│   ├── r_run.schema.json
│   ├── git_clone.schema.json
│   ├── git_diff.schema.json
│   ├── code_test.schema.json
│   ├── code_build.schema.json
│   ├── image_process.schema.json
│   ├── image_ocr.schema.json
│   ├── audio_transcribe.schema.json
│   ├── video_extract.schema.json
│   ├── pdf_render.schema.json
│   ├── ui_parse.schema.json
│   ├── sql_query.schema.json
│   ├── screenshot_capture.schema.json
│   ├── computer_action.schema.json
│   ├── desktop_run.schema.json
│   ├── browser_run.schema.json
│   ├── browser_screenshot.schema.json
│   ├── browser_pdf.schema.json
│   ├── browser_click.schema.json
│   └── browser_type.schema.json
│
└── scripts/
    ├── new-tool.sh                            # Scaffold new tool from _template
    ├── build-all.sh                           # Build all WASM + container images
    ├── test-all.sh                            # Run all tool tests
    └── publish.sh                             # Push images to GCR + upload .wasm to MinIO
```

---

## Tool Anatomy

### Tier 1 — WASM Tool Structure

Every WASM tool has this shape:

```
tool_name/
├── tool.json          ← manifest (name, tier, timeout_ms, input/output schema)
├── src/
│   └── main.py        ← Pyodide Python (or AssemblyScript .ts for perf-critical)
├── build.sh           ← builds → dist/tool_name.wasm (or uses pyodide loader)
├── dist/              ← compiled .wasm binary (gitignored, produced by CI)
└── test/
    ├── input.json     ← example input
    └── expected.json  ← expected output for unit test
```

**tool.json example** (`json_parser`):
```json
{
  "name": "json_parser",
  "tier": "wasm",
  "timeout_ms": 5000,
  "description": "Parse and transform JSON using jq-like expressions",
  "input_schema": {
    "type": "object",
    "required": ["json", "expression"],
    "properties": {
      "json":       { "type": "string", "description": "Raw JSON string" },
      "expression": { "type": "string", "description": "jq expression, e.g. .items[].name" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "result": { "type": "string" },
      "error":  { "type": "string" }
    }
  }
}
```

---

### Tier 2 — Headless Tool Structure

Every headless tool is a container with a gRPC server:

```
tool_name/
├── tool.json
├── Dockerfile
├── src/
│   ├── runner.py      ← gRPC server: implements ExecutionService.Execute()
│   └── tool.py        ← actual tool logic (pure function, easy to test)
├── requirements.txt
├── proto/             ← symlink → ../../shared/proto/
└── test/
    ├── test_tool.py   ← pytest unit tests (import tool.py directly)
    └── input.json
```

**runner.py pattern** (all Tier 2 tools follow this):
```python
import grpc
import json
from concurrent import futures
from proto import execution_pb2, execution_pb2_grpc
from tool import run   # pure tool function

class ExecutionServicer(execution_pb2_grpc.ExecutionServiceServicer):
    def Execute(self, request, context):
        input_data = json.loads(request.input_json)
        try:
            result = run(input_data)
            return execution_pb2.ExecuteResult(
                job_id=request.job_id,
                exit_code=0,
                stdout=json.dumps(result),
            )
        except Exception as e:
            return execution_pb2.ExecuteResult(
                job_id=request.job_id,
                exit_code=1,
                stderr=str(e),
            )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    execution_pb2_grpc.add_ExecutionServiceServicer_to_server(ExecutionServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
```

---

### Tier 3 — GUI Tool Structure

Every GUI tool runs inside the Firecracker VM image:

```
tool_name/
├── tool.json
├── Dockerfile.desktop   ← FROM ubuntu:22.04-minimal + Xvfb + XFCE + grpc server
├── src/
│   ├── runner.py        ← gRPC: Execute + TakeScreenshot + SendInput
│   └── tool.py          ← tool logic (uses xdotool / scrot / Playwright)
└── test/
    ├── test_tool.py
    └── input.json
```

---

## Per-Tool Runtime Dependencies

### Tier 1 Runtimes
| Package | Version | Used by |
|---|---|---|
| Pyodide | 0.26 | python_snippet, all Python WASM tools |
| AssemblyScript | 0.27 | perf-critical utilities |
| Wasmtime | 22 | host runtime in platform-core |
| emscripten | 3.1 | C/C++ WASM compilation |
| wasm-pack | 0.13 | Rust → WASM |
| WASI HTTP fetch polyfill | latest | web_fetch, web_search |
| JSON Schema Draft 7 | — | input/output validation |

### Tier 2 Runtimes
| Package | Version | Used by |
|---|---|---|
| python:3.12-slim | 3.12 | python_run, all Python tools |
| node:20-slim | 20 | nodejs_run |
| Deno | 1.44 | deno_run |
| R | 4.4 | r_run |
| FFmpeg (static) | 7.0 | video_extract |
| Tesseract | 5.3 | image_ocr |
| Pillow | 10 | image_process |
| Sharp | 0.33 | image_process (Node path) |
| Whisper.cpp | latest | audio_transcribe |
| OmniParser v2 ONNX | 1.18 | ui_parse |
| psycopg3 | latest | sql_query (PostgreSQL) |
| pymongo | latest | sql_query (MongoDB) |
| grpcio | 1.64 | all gRPC servers |

### Tier 3 Runtimes
| Package | Version | Used by |
|---|---|---|
| Firecracker KVM | 1.8 | VM host |
| Ubuntu 22.04 LTS minimal | — | Base OS |
| Xvfb | — | Virtual display |
| XFCE | 4.18 | Desktop environment |
| Playwright | 1.45 | browser_* tools |
| Chromium | 126 | browser_* tools |
| scrot | 1.10 | screenshot_capture |
| xdotool | 3.20 | computer_action |
| TigerVNC | 1.13 | VNC server |
| noVNC | 1.5 | Browser VNC client |
| FC Snapshot API | — | 125ms restore |

---

## CI Pipeline per Tool

```
push to main
  │
  ├── Tier 1 tools:  run test/ input.json → validate output matches expected.json
  │                  build .wasm → upload to MinIO artifacts/{tool_name}.wasm
  │
  ├── Tier 2 tools:  pytest test/ inside Docker image
  │                  docker build → push to GCR gcr.io/platform/{tool_name}:sha-{sha}
  │
  └── Tier 3 tools:  integration test inside local Firecracker VM (kind + kata-fc)
                     docker build Dockerfile.desktop → push to GCR
```

---

## Adding a New Tool (quick-start)

```bash
# 1. Scaffold
./scripts/new-tool.sh --tier tier2-headless --name my_new_tool

# 2. Implement
cd tier2-headless/my_new_tool
# edit src/tool.py with your logic
# edit tool.json with input/output schema

# 3. Test
pytest test/ -v

# 4. Build & push
./scripts/build-all.sh --tool my_new_tool

# 5. Register in platform-core
# Insert row in PostgreSQL tools table:
#   INSERT INTO tools (tool_name, tier, container_image, input_schema, timeout_ms)
#   VALUES ('my_new_tool', 'headless', 'gcr.io/platform/my_new_tool:latest', '{}', 30000);
```
