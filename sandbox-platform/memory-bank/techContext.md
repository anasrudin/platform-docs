# Tech Context

## Go Dependencies (go.mod)

| Package | Version | Used For |
|---------|---------|----------|
| `github.com/gofiber/fiber/v2` | v2.52.5 | HTTP API server |
| `github.com/google/uuid` | v1.6.0 | Job ID generation |
| `github.com/minio/minio-go/v7` | v7.0.74 | Object storage (tool artifacts) |
| `github.com/prometheus/client_golang` | v1.20.0 | Metrics exposition |
| `github.com/redis/go-redis/v9` | v9.6.1 | Job queue + node registry |
| `github.com/spf13/viper` | v1.19.0 | Config file + env var override |

## External Binaries (must be installed on node)

| Binary | Purpose | Install |
|--------|---------|---------|
| `wasmtime` | Execute WASM modules | https://wasmtime.dev |
| `firecracker` | MicroVM runtime | https://github.com/firecracker-microvm/firecracker |
| `docker` | GUI container runtime | https://docs.docker.com |

## Config Keys (all under `SANDBOX_` env prefix)

```yaml
server:
  port: 8080
  shutdown_timeout_seconds: 30
  jwt_public_key_path: ""  # empty = dev mode

redis:
  url: redis://localhost:6379
  job_stream: jobs
  consumer_group: platform

minio:
  endpoint: localhost:9000
  access_key: minioadmin
  secret_key: minioadmin
  bucket: platform
  use_ssl: false

metrics:
  port: 9090

platform:
  namespace: default
```

Environment override example:
```bash
SANDBOX_SERVER_PORT=9090
SANDBOX_REDIS_URL=redis://prod:6379
SANDBOX_SERVER_JWT_PUBLIC_KEY_PATH=/run/secrets/jwt.pem
```

## Node Agent Flags

```
--node-id   string   Unique identifier for this node (required)
--redis     string   Redis URL (default: redis://localhost:6379)
--data-dir  string   Data directory for VM images and WASM modules (default: /var/sandbox)
```

## Data Directory Layout on Node

```
/var/sandbox/
  wasm-modules/
    html_parse.wasm
    json_parse.wasm
    markdown_convert.wasm
    docx_generate.wasm
  snapshots/
    default/
      state          ← Firecracker VM state
      mem            ← Firecracker memory snapshot
      meta.json      ← Build metadata
  vm-images/
    rootfs.ext4      ← Base rootfs for VM builds
  kernels/
    vmlinux          ← Uncompressed kernel for Firecracker
```

## Local Dev Services

| Service | Port | Credentials |
|---------|------|-------------|
| Redis 7 | 6379 | no password |
| MinIO | 9000 (API) 9001 (console) | minioadmin / minioadmin |
| Prometheus | 9090 | open |

## Metrics Exposed

| Metric | Type | Labels |
|--------|------|--------|
| `sandbox_http_requests_total` | Counter | method, path, status |
| `sandbox_http_request_duration_seconds` | Histogram | method, path |
| `sandbox_jobs_submitted_total` | Counter | tool, tier |
| `sandbox_jobs_completed_total` | Counter | tool, tier, status |
| `sandbox_job_duration_seconds` | Histogram | tier |
| `sandbox_active_vms` | Gauge | — |
| `sandbox_active_gui_containers` | Gauge | — |
| `sandbox_queue_depth` | Gauge | stream |

## Tool I/O

```
Input:  TOOL_INPUT env var = JSON string
Output: stdout = JSON string with at minimum {"exit_code": N}
Errors: stderr (captured in RuntimeResult.Stderr)
```

## Docker Desktop-Runner Image Contents

```
ubuntu:22.04
  xvfb, x11vnc, xdotool
  chromium-browser, chromium-chromedriver
  python3, pip3
  libreoffice (calc, writer, impress)
  playwright 1.44.0
  selenium 4.21.0
  beautifulsoup4, openpyxl, python-docx
```
