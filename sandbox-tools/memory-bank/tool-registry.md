# Tool Registry

> Last updated: 2026-03-11

## WASM Tools (Tier 1 — Fast Path)

| Tool Name | Runtime | Skill | Entry Point | Timeout | Memory | Status |
|---|---|---|---|---|---|---|
| `html_parse` | wasm | scraping | `main.rs` | 5s | 64MB | 🔲 |
| `json_parse` | wasm | data | `main.rs` | 5s | 64MB | 🔲 |
| `markdown_convert` | wasm | document | `main.rs` | 3s | 64MB | 🔲 |
| `csv_process` | wasm | data | `main.rs` | 10s | 64MB | 🔲 |
| `xml_parse` | wasm | data | `main.rs` | 5s | 64MB | 🔲 |
| `text_process` | wasm | data | `main.rs` | 3s | 64MB | 🔲 |
| `yaml_parse` | wasm | data | `main.rs` | 3s | 64MB | 🔲 |
| `docx_generate` | wasm | document | `main.py` | 10s | 128MB | 🔲 |
| `xlsx_generate` | wasm | document | `main.py` | 10s | 128MB | 🔲 |
| `http_request` | wasm | integration | `main.rs` | 15s | 64MB | 🔲 |
| `llm_call` | wasm | ai | `main.py` | 30s | 128MB | 🔲 |

## Firecracker Tools (Tier 2 — Secure Compute)

| Tool Name | Runtime | Skill | Entry Point | Timeout | Memory | Snapshot | Status |
|---|---|---|---|---|---|---|---|
| `python_exec` | firecracker | coding | `main.py` | 60s | 256MB | `python-v1` | 🔲 |
| `bash_run` | firecracker | terminal | `main.py` | 30s | 128MB | `bash-v1` | 🔲 |
| `nodejs_run` | firecracker | coding | `main.js` | 60s | 256MB | `node-v1` | 🔲 |
| `git_clone` | firecracker | coding | `main.py` | 120s | 256MB | `bash-v1` | 🔲 |
| `git_diff` | firecracker | coding | `main.py` | 30s | 128MB | `bash-v1` | 🔲 |
| `code_test` | firecracker | coding | `main.py` | 120s | 512MB | `python-v1` | 🔲 |
| `file_ops` | firecracker | terminal | `main.py` | 10s | 128MB | `bash-v1` | 🔲 |
| `image_process` | firecracker | media | `main.py` | 30s | 256MB | `python-v1` | 🔲 |
| `audio_transcribe` | firecracker | media | `main.py` | 180s | 512MB | `whisper-v1` | 🔲 |
| `sql_query` | firecracker | data | `main.py` | 30s | 256MB | `python-v1` | 🔲 |

## GUI Tools (Tier 3 — Interactive)

| Tool Name | Runtime | Skill | Entry Point | Timeout | Memory | Status |
|---|---|---|---|---|---|---|
| `browser_open` | gui | scraping | `script.js` | 60s | 512MB | 🔲 |
| `web_scrape` | gui | scraping | `script.js` | 60s | 512MB | 🔲 |
| `screenshot` | gui | scraping | `script.js` | 30s | 512MB | 🔲 |
| `form_automation` | gui | automation | `script.js` | 120s | 512MB | 🔲 |
| `browser_pdf` | gui | document | `script.js` | 30s | 512MB | 🔲 |
| `browser_click` | gui | automation | `script.js` | 30s | 512MB | 🔲 |

## Skill → Tool Mapping

```yaml
coding:
  primary: python_exec
  fallback: nodejs_run
  tools: [python_exec, nodejs_run, bash_run]

scraping:
  primary: html_parse
  fallback: web_scrape
  tools: [html_parse, web_scrape, browser_open]

document:
  primary: docx_generate
  tools: [docx_generate, xlsx_generate, markdown_convert, browser_pdf]

data:
  primary: json_parse
  tools: [json_parse, csv_process, xml_parse, yaml_parse, sql_query]

terminal:
  primary: bash_run
  tools: [bash_run, file_ops]

media:
  primary: image_process
  tools: [image_process, audio_transcribe, screenshot]

ai:
  primary: llm_call
  tools: [llm_call]

automation:
  primary: form_automation
  tools: [form_automation, browser_click]
```

## Snapshot Templates

| Template | Runtime Installed | Base OS |
|---|---|---|
| `python-v1` | Python 3.12 + pip + requests, pandas, numpy | Ubuntu 22.04 minimal |
| `node-v1` | Node.js 20 + npm | Ubuntu 22.04 minimal |
| `bash-v1` | Bash 5 + coreutils + curl | Ubuntu 22.04 minimal |
| `whisper-v1` | Python 3.12 + whisper.cpp | Ubuntu 22.04 minimal |
