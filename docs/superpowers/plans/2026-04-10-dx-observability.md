# DX & Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Solve dua pain point: setup satu perintah untuk developer baru, dan request tracing end-to-end dari HTTP masuk sampai VM execute via Jaeger.

**Architecture:** Services di-reorganisasi per kategori (data/controller/monitoring) dengan Docker Compose `include`. OTEL spans ditambahkan ke pool acquire dan snapshot download di layer `orchestrator/`. Request ID di-propagate lewat middleware baru dan bound ke semua log via structlog contextvars.

**Tech Stack:** Docker Compose v2.20+ (include directive), Jaeger all-in-one 1.57, OpenTelemetry (sudah ada adapter di `adapters/tracing/`), structlog contextvars, FastAPI `BaseHTTPMiddleware`.

**Spec:** `docs/superpowers/specs/2026-04-10-dx-observability-design.md`

---

## File Map

| File | Action | Tanggung jawab |
|---|---|---|
| `services/docker-compose.yml` | Modify | Root compose — include sub-composes |
| `services/data/docker-compose.yml` | Create | postgres, redis, minio |
| `services/controller/docker-compose.yml` | Create | consul |
| `services/monitoring/docker-compose.yml` | Create | jaeger all-in-one |
| `services/monitoring/jaeger/config.yaml` | Create | Jaeger sampling config |
| `.env.example` | Create | Semua vars dari settings.py dengan komentar |
| `Makefile` | Modify | Tambah `setup`, `services-data`, `services-controller`, `services-monitoring` |
| `sandbox-worker/src/config/settings.py` | Modify | Tambah `dev_mode` ke `APIConfig`, tambah `node_id` ke `APIConfig` |
| `sandbox-worker/src/api/app.py` | Modify | Dev/prod log config, register `RequestIDMiddleware` |
| `sandbox-worker/src/api/middleware/request_id.py` | Create | `RequestIDMiddleware` — UUID per request, bound ke structlog |
| `sandbox-worker/src/orchestrator/lifecycle.py` | Modify | OTEL span `pool.acquire` |
| `sandbox-worker/src/orchestrator/snapshot.py` | Modify | OTEL span `vm.restore_snapshot` |
| `sandbox-worker/src/adapters/tracing/noop.py` | Read | Pastikan `_NoopSpan` bisa di-import di tests |
| `sandbox-worker/pyproject.toml` | Modify | Tambah `ruff`, `mypy` ke dev deps |
| `sandbox-worker/tests/unit/test_request_id_middleware.py` | Create | Tests untuk `RequestIDMiddleware` |
| `sandbox-worker/tests/unit/test_lifecycle_spans.py` | Create | Tests untuk OTEL spans di lifecycle |
| `sandbox-worker/tests/unit/test_snapshot_spans.py` | Create | Tests untuk OTEL spans di snapshot |

---

## Task 1: Reorganisasi `services/` — data layer

**Files:**
- Create: `services/data/docker-compose.yml`
- Create: `services/data/postgres/` (symlink atau copy migrations dari `services/postgres/`)

- [ ] **Step 1: Buat `services/data/docker-compose.yml`**

```yaml
# services/data/docker-compose.yml
services:
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - platform-net

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: platform
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../postgres/migrations/001_init.sql:/docker-entrypoint-initdb.d/001_init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - platform-net

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - platform-net

volumes:
  minio_data:
  postgres_data:

networks:
  platform-net:
    external: true
```

- [ ] **Step 2: Buat `services/controller/docker-compose.yml`**

```yaml
# services/controller/docker-compose.yml
services:
  consul:
    image: hashicorp/consul:1.17
    command: "agent -dev -ui -client=0.0.0.0"
    ports:
      - "8500:8500"
      - "8600:8600/udp"
    healthcheck:
      test: ["CMD", "consul", "members"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - platform-net

networks:
  platform-net:
    external: true
```

- [ ] **Step 3: Pastikan folder `services/postgres/` ada dengan migration**

Cek apakah file migration sudah ada:
```bash
ls services/postgres/migrations/ 2>/dev/null || echo "MISSING"
```

Kalau `MISSING`, buat symlink:
```bash
mkdir -p services/postgres
ln -sf ../nomad/jobs services/postgres/migrations 2>/dev/null || true
```

Catatan: kalau migration aslinya ada di path lain, sesuaikan path volume di postgres service di atas.

- [ ] **Step 4: Commit**

```bash
git add services/data/ services/controller/
git commit -m "feat(services): split data and controller compose layers"
```

---

## Task 2: Monitoring layer — Jaeger

**Files:**
- Create: `services/monitoring/docker-compose.yml`
- Create: `services/monitoring/jaeger/config.yaml`

- [ ] **Step 1: Buat `services/monitoring/jaeger/config.yaml`**

```yaml
# services/monitoring/jaeger/config.yaml
service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger_storage_exporter]

extensions:
  jaeger_storage:
    backends:
      memstore:
        memory:
          max_traces: 100000
  jaeger_query:
    storage:
      traces: memstore
    ui:
      config_file: ""

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

exporters:
  jaeger_storage_exporter:
    trace_storage: memstore
```

- [ ] **Step 2: Buat `services/monitoring/docker-compose.yml`**

```yaml
# services/monitoring/docker-compose.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.57
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
      SPAN_STORAGE_TYPE: memory
      MEMORY_MAX_TRACES: "100000"
    ports:
      - "16686:16686"   # Jaeger UI — buka di browser
      - "4317:4317"     # OTEL gRPC
      - "4318:4318"     # OTEL HTTP
    networks:
      - platform-net

networks:
  platform-net:
    external: true
```

Catatan: `all-in-one` sudah embed storage, jadi `config.yaml` diatas tidak di-mount (dipakai sebagai referensi saja jika nanti migrasi ke jaeger v2). Simpan file tetap untuk dokumentasi.

- [ ] **Step 3: Update root `services/docker-compose.yml` — ganti isi dengan include**

Ganti seluruh isi `services/docker-compose.yml`:

```yaml
# services/docker-compose.yml
# Root compose — include semua layer
# Jalankan: docker compose up -d
# Atau per layer: docker compose -f data/docker-compose.yml up -d

include:
  - path: data/docker-compose.yml
  - path: controller/docker-compose.yml
  - path: monitoring/docker-compose.yml

networks:
  platform-net:
    driver: bridge
```

- [ ] **Step 4: Buat shared network dulu sebelum test**

```bash
docker network create platform-net 2>/dev/null || true
```

- [ ] **Step 5: Verify compose config valid**

```bash
cd services && docker compose config --quiet
```

Expected: tidak ada error output.

- [ ] **Step 6: Test jaeger jalan**

```bash
cd services && docker compose -f monitoring/docker-compose.yml up -d
sleep 3
curl -sf http://localhost:16686/ | head -5
```

Expected: HTML response dari Jaeger UI.

```bash
cd services && docker compose -f monitoring/docker-compose.yml down
```

- [ ] **Step 7: Commit**

```bash
git add services/monitoring/ services/docker-compose.yml
git commit -m "feat(services): add monitoring layer with Jaeger, reorganize compose"
```

---

## Task 3: Update root Makefile — targets per layer + `make setup`

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Tambah targets ke root `Makefile`**

Tambahkan setelah blok `services-down:` yang sudah ada:

```makefile
services-data:
	@echo ">>> Starting data services (postgres, redis, minio)..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose -f data/docker-compose.yml up -d

services-controller:
	@echo ">>> Starting controller services (consul)..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose -f controller/docker-compose.yml up -d

services-monitoring:
	@echo ">>> Starting monitoring services (jaeger)..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose -f monitoring/docker-compose.yml up -d

services-up:
	@echo ">>> Starting all services..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose up -d
	@sleep 5
	@$(MAKE) services-status

setup:
	@echo ">>> [1/4] Copying .env.example → sandbox-worker/.env (jika belum ada)..."
	@[ -f sandbox-worker/.env ] || cp sandbox-worker/.env.example sandbox-worker/.env
	@echo ">>> [2/4] Installing worker deps..."
	cd sandbox-worker && uv venv .venv && uv pip install -e ".[dev]"
	@echo ">>> [3/4] Starting data + monitoring services..."
	$(MAKE) services-data services-monitoring
	@echo ">>> [4/4] Checking service health..."
	@sleep 5
	@$(MAKE) services-status
	@echo ""
	@echo "Setup selesai. Langkah berikutnya:"
	@echo "  make worker-run   — start platform API"
	@echo "  open http://localhost:16686  — Jaeger UI"
```

- [ ] **Step 2: Verify targets bisa di-list**

```bash
make help | grep -E "setup|services-data|services-monitoring"
```

Expected: ketiga target muncul (atau tidak error kalau help belum ada grep pattern).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(make): add setup target and per-layer service targets"
```

---

## Task 4: Buat `.env.example`

**Files:**
- Create: `sandbox-worker/.env.example`

- [ ] **Step 1: Buat `sandbox-worker/.env.example`**

```bash
# sandbox-worker/.env.example
# Copy ke .env: cp .env.example .env
# Semua nilai di sini adalah default untuk dev lokal.
# JANGAN commit .env — sudah ada di .gitignore

# ── API ────────────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8080
API_WORKERS=1
DEV_MODE=true            # true = human-readable logs + /debug/state endpoint
NODE_ID=                 # opsional: identifikasi node di log (default: hostname)

# ── Firecracker ────────────────────────────────────────────────────────────────
FC_MODE=sim              # sim = aman untuk macOS (tidak butuh /dev/kvm)
                         # real = butuh Linux + /dev/kvm
FC_POOL_SIZE=2
FC_DEV_MODE=true
FC_BINARY_PATH=/usr/bin/firecracker
FC_KERNEL_PATH=/opt/platform/vmlinux
FC_ROOTFS_PATH=/opt/platform/rootfs.ext4
FC_VSOCK_CID_BASE=100
FC_SNAPSHOT_BUCKET=platform-snapshots

# ── WASM ───────────────────────────────────────────────────────────────────────
WASM_MODE=sim            # sim = tidak butuh wasmtime binary
WASM_MODULE_DIR=/opt/platform/wasm

# ── GUI (Chromium) ─────────────────────────────────────────────────────────────
GUI_MODE=sim
CHROME_PATH=/usr/bin/chromium-browser
VNC_PORT_BASE=5900

# ── Redis ──────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
REDIS_SESSION_PREFIX=session:
REDIS_SESSION_TTL=3600

# ── PostgreSQL ─────────────────────────────────────────────────────────────────
DATABASE_URL=postgres://postgres:postgres@localhost:5432/platform?sslmode=disable

# ── MinIO / Artifact Storage ───────────────────────────────────────────────────
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=platform-artifacts

# ── Packages ───────────────────────────────────────────────────────────────────
PACKAGES_LOCAL_DIR=      # kosong = /tmp/platform-packages
PACKAGES_MINIO_PREFIX=packages

# ── Storage (artifact lokal fallback) ─────────────────────────────────────────
ARTIFACTS_LOCAL_DIR=     # kosong = /tmp/platform-artifacts

# ── Observability — OpenTelemetry ──────────────────────────────────────────────
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=sandbox-platform

# ── Streaming ──────────────────────────────────────────────────────────────────
STREAM_MAX_TIMEOUT=300
STREAM_BUFFER_SIZE=4096

# ── Workspace ──────────────────────────────────────────────────────────────────
WORKSPACE_DRIVER=sync
WORKSPACE_MAX_SIZE_MB=1024
WORKSPACE_LOCAL_DIR=     # kosong = /tmp/platform-workspaces

# ── Hibernation ────────────────────────────────────────────────────────────────
HIBERNATE_ENABLED=false
HIBERNATE_IDLE_TIMEOUT=300
HIBERNATE_SCAN_INTERVAL=60
HIBERNATE_TTL=86400

# ── Audit ──────────────────────────────────────────────────────────────────────
AUDIT_BACKEND=stdout     # stdout | postgres | s3

# ── Workflow ───────────────────────────────────────────────────────────────────
WORKFLOW_MAX_STEPS=20
WORKFLOW_MAX_TIMEOUT=600
WORKFLOW_MAX_PARALLEL=5

# ── Rate Limiting ──────────────────────────────────────────────────────────────
RATELIMIT_ENABLED=false
RATELIMIT_BACKEND=memory
DEFAULT_MAX_RPM=30
DEFAULT_MAX_SESSIONS=2

# ── Feature flags (semua default off — aman untuk dev lokal) ──────────────────
CONSUL_ENABLED=false     # true = register ke Consul, butuh Consul running
SCALER_ENABLED=false     # true = jalankan background auto-scaler
MTLS_ENABLED=false       # true = reject request tanpa client cert
TENANT_ISOLATION=false   # true = wajib X-Tenant-ID header
```

- [ ] **Step 2: Pastikan `.env` ada di `.gitignore`**

```bash
grep -q "^\.env$" sandbox-worker/.gitignore || echo ".env" >> sandbox-worker/.gitignore
```

- [ ] **Step 3: Commit**

```bash
git add sandbox-worker/.env.example sandbox-worker/.gitignore
git commit -m "feat(config): add .env.example with all settings documented"
```

---

## Task 5: Tambah `dev_mode` dan `node_id` ke settings.py

**Files:**
- Modify: `sandbox-worker/src/config/settings.py`

- [ ] **Step 1: Tambah `dev_mode` dan `node_id` ke `APIConfig`**

Di `sandbox-worker/src/config/settings.py`, ubah `APIConfig`:

```python
# ── API Server ─────────────────────────────────────────────────────────────────

@dataclass
class APIConfig:
    host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("API_PORT", 8080))
    workers: int = field(default_factory=lambda: _env_int("API_WORKERS", 1))
    dev_mode: bool = field(default_factory=lambda: _env_bool("DEV_MODE"))
    node_id: str = field(default_factory=lambda: _env("NODE_ID", "") or __import__("socket").gethostname())
    health_port: int = field(default_factory=lambda: _env_int("API_HEALTH_PORT", 8081))
```

- [ ] **Step 2: Verify settings parse benar**

```bash
cd sandbox-worker && .venv/bin/python -c "
from src.config.settings import settings
print('dev_mode:', settings.api.dev_mode)
print('node_id:', settings.api.node_id)
"
```

Expected: `dev_mode: False` (karena DEV_MODE belum di-set), `node_id: <hostname>`.

- [ ] **Step 3: Commit**

```bash
git add sandbox-worker/src/config/settings.py
git commit -m "feat(config): add dev_mode and node_id to APIConfig"
```

---

## Task 6: Dev-mode logging di `api/app.py`

**Files:**
- Modify: `sandbox-worker/src/api/app.py`

- [ ] **Step 1: Ganti blok `structlog.configure` di top-level `app.py`**

Di `api/app.py`, hapus blok configure awal:
```python
# HAPUS blok ini (baris 44-51):
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
```

Ganti dengan fungsi yang dipanggil di awal `lifespan`:

```python
def _configure_logging(dev_mode: bool) -> None:
    """Konfigurasi structlog berdasarkan mode."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="%H:%M:%S.%f" if dev_mode else "iso"),
    ]
    if dev_mode:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
            processors=shared_processors + [structlog.dev.ConsoleRenderer()],
        )
    else:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            processors=shared_processors + [structlog.processors.JSONRenderer()],
        )
```

Panggil di awal `lifespan`, sebelum `init_tracer`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings
    _configure_logging(cfg.api.dev_mode)   # ← tambahkan baris ini
    
    # Tracing
    init_tracer(
        driver=cfg.tracing.enabled and "otel" or "noop",
        ...
    )
    ...
```

- [ ] **Step 2: Test manual — jalankan dengan DEV_MODE=true**

```bash
cd sandbox-worker && DEV_MODE=true .venv/bin/python -c "
import logging
import structlog
from config.settings import settings
from api.app import _configure_logging
_configure_logging(settings.api.dev_mode)
log = structlog.get_logger()
log.info('test log', key='value', number=42)
"
```

Expected dengan `DEV_MODE=false` (default): JSON output.
Expected dengan `DEV_MODE=true`: colored output, human-readable.

- [ ] **Step 3: Commit**

```bash
git add sandbox-worker/src/api/app.py
git commit -m "feat(logging): dev-mode ConsoleRenderer, prod JSON — configurable via DEV_MODE"
```

---

## Task 7: `RequestIDMiddleware`

**Files:**
- Create: `sandbox-worker/src/api/middleware/request_id.py`
- Modify: `sandbox-worker/src/api/app.py`
- Create: `sandbox-worker/tests/unit/test_request_id_middleware.py`

- [ ] **Step 1: Tulis failing test dulu**

Buat `sandbox-worker/tests/unit/test_request_id_middleware.py`:

```python
"""Tests for RequestIDMiddleware."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app():
    from api.middleware.request_id import RequestIDMiddleware
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


class TestRequestIDMiddleware:
    def test_response_has_request_id_header(self):
        client = TestClient(_make_app())
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_request_id_is_8_chars(self):
        client = TestClient(_make_app())
        resp = client.get("/ping")
        req_id = resp.headers["x-request-id"]
        assert len(req_id) == 8

    def test_client_provided_request_id_is_echoed(self):
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Request-ID": "custom-1"})
        assert resp.headers["x-request-id"] == "custom-1"

    def test_each_request_gets_unique_id(self):
        client = TestClient(_make_app())
        ids = {client.get("/ping").headers["x-request-id"] for _ in range(5)}
        assert len(ids) == 5  # semua unik
```

- [ ] **Step 2: Jalankan test — pastikan FAIL**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/test_request_id_middleware.py -v
```

Expected: `ImportError: cannot import name 'RequestIDMiddleware'`

- [ ] **Step 3: Implementasi `RequestIDMiddleware`**

Buat `sandbox-worker/src/api/middleware/request_id.py`:

```python
"""RequestIDMiddleware — propagate X-Request-ID ke semua log dalam satu request."""
from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate atau ambil X-Request-ID dari header, bind ke structlog context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Gunakan ID dari client kalau ada, generate baru kalau tidak ada
        request_id = request.headers.get("X-Request-ID") or str(uuid4())[:8]
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

- [ ] **Step 4: Jalankan test — pastikan PASS**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/test_request_id_middleware.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Register middleware di `api/app.py`**

Di `create_app()`, tambahkan `RequestIDMiddleware` sebagai middleware **pertama** (dieksekusi terakhir karena LIFO):

```python
from api.middleware.request_id import RequestIDMiddleware

def create_app() -> FastAPI:
    app = FastAPI(title="sandbox-platform-worker", lifespan=lifespan)

    app.add_middleware(RequestIDMiddleware)   # ← tambahkan baris ini
    app.add_middleware(TracingMiddleware)
    _auth_cfg = auth_config_from_env()
    app.add_middleware(TenantAuthMiddleware, enabled=_auth_cfg["enabled"])
    ...
```

- [ ] **Step 6: Jalankan seluruh unit tests**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/ -v --tb=short
```

Expected: semua tests PASS termasuk test baru.

- [ ] **Step 7: Commit**

```bash
git add sandbox-worker/src/api/middleware/request_id.py \
        sandbox-worker/src/api/app.py \
        sandbox-worker/tests/unit/test_request_id_middleware.py
git commit -m "feat(middleware): add RequestIDMiddleware — X-Request-ID propagated to all logs"
```

---

## Task 8: OTEL spans di `VMLifecycleManager.acquire()`

**Files:**
- Modify: `sandbox-worker/src/orchestrator/lifecycle.py`
- Create: `sandbox-worker/tests/unit/test_lifecycle_spans.py`

- [ ] **Step 1: Tulis failing test**

Buat `sandbox-worker/tests/unit/test_lifecycle_spans.py`:

```python
"""Tests — OTEL spans di VMLifecycleManager.acquire()."""
from __future__ import annotations

import pytest
from adapters.tracing import init_tracer, reset_tracer
from adapters.tracing.noop import _NoopSpan


class TestLifecycleSpans:
    def setup_method(self):
        reset_tracer()
        init_tracer(driver="noop")

    def teardown_method(self):
        reset_tracer()

    def test_acquire_emits_pool_acquire_span(self, monkeypatch):
        """acquire() harus emit span 'pool.acquire'."""
        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append((name, attrs or {}))
                yield _NoopSpan()

        monkeypatch.setattr("orchestrator.lifecycle.get_tracer", lambda: RecordingTracer())

        class MockVM:
            pass

        class MockPool:
            available = 1
            size = 2
            def acquire(self, timeout=30.0):
                return MockVM()

        from orchestrator.lifecycle import VMLifecycleManager
        mgr = VMLifecycleManager.__new__(VMLifecycleManager)
        mgr._pool = MockPool()
        mgr._pool_size = 2
        mgr._snapshot_name = "test-snap"
        mgr._dev_mode = True

        vm = mgr.acquire(timeout=5.0)

        assert vm is not None
        span_names = [s[0] for s in spans_started]
        assert "pool.acquire" in span_names

    def test_acquire_span_has_pool_size_attribute(self, monkeypatch):
        """Span pool.acquire harus punya attribute pool_size."""
        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append((name, attrs or {}))
                yield _NoopSpan()

        monkeypatch.setattr("orchestrator.lifecycle.get_tracer", lambda: RecordingTracer())

        class MockVM:
            pass

        class MockPool:
            available = 1
            size = 2
            def acquire(self, timeout=30.0):
                return MockVM()

        from orchestrator.lifecycle import VMLifecycleManager
        mgr = VMLifecycleManager.__new__(VMLifecycleManager)
        mgr._pool = MockPool()
        mgr._pool_size = 2
        mgr._snapshot_name = "test-snap"
        mgr._dev_mode = True

        mgr.acquire(timeout=5.0)

        pool_span = next(s for s in spans_started if s[0] == "pool.acquire")
        assert pool_span[1].get("pool_size") == 2
```

- [ ] **Step 2: Jalankan test — pastikan FAIL**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/test_lifecycle_spans.py -v
```

Expected: FAIL — span `pool.acquire` belum ada.

- [ ] **Step 3: Tambah span ke `VMLifecycleManager.acquire()`**

Di `sandbox-worker/src/orchestrator/lifecycle.py`, tambahkan import dan wrap `acquire()`:

```python
from adapters.tracing import get_tracer   # tambahkan import ini

class VMLifecycleManager:
    # ... (tidak ada perubahan di __init__, start, release, stop)

    def acquire(self, timeout: float = 30.0):
        if self._pool is None:
            raise RuntimeError("VMLifecycleManager not started")
        tracer = get_tracer()
        with tracer.start_span("pool.acquire", {
            "pool_size": self._pool_size,
            "snapshot_name": self._snapshot_name,
            "timeout_s": timeout,
        }) as span:
            vm = self._pool.acquire(timeout=timeout)
            # Pool exposes .available kalau ada, kalau tidak skip
            if hasattr(self._pool, "available"):
                span.set_attribute("pool_available", self._pool.available)
            return vm
```

- [ ] **Step 4: Jalankan test — pastikan PASS**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/test_lifecycle_spans.py -v
```

Expected: 2 tests PASSED.

- [ ] **Step 5: Jalankan seluruh unit tests — pastikan tidak ada regresi**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/ -v --tb=short
```

Expected: semua tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sandbox-worker/src/orchestrator/lifecycle.py \
        sandbox-worker/tests/unit/test_lifecycle_spans.py
git commit -m "feat(tracing): add pool.acquire OTEL span to VMLifecycleManager"
```

---

## Task 9: OTEL spans di `SnapshotDownloader.ensure()`

**Files:**
- Modify: `sandbox-worker/src/orchestrator/snapshot.py`
- Create: `sandbox-worker/tests/unit/test_snapshot_spans.py`

- [ ] **Step 1: Tulis failing test**

Buat `sandbox-worker/tests/unit/test_snapshot_spans.py`:

```python
"""Tests — OTEL spans di SnapshotDownloader.ensure()."""
from __future__ import annotations

import pytest
from adapters.tracing import init_tracer, reset_tracer
from adapters.tracing.noop import _NoopSpan


class TestSnapshotSpans:
    def setup_method(self):
        reset_tracer()
        init_tracer(driver="noop")

    def teardown_method(self):
        reset_tracer()

    def test_ensure_cache_hit_emits_span(self, monkeypatch, tmp_path):
        """ensure() harus emit span vm.restore_snapshot saat cache hit."""
        import json, os
        from orchestrator.snapshot import SnapshotDownloader, SnapshotPaths

        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append((name, attrs or {}))
                yield _NoopSpan()

        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: RecordingTracer())

        # Buat fake cached snapshot
        snap_dir = tmp_path / "mysnap"
        snap_dir.mkdir()
        (snap_dir / "vmstate.bin").write_bytes(b"state")
        (snap_dir / "memory.bin").write_bytes(b"mem")
        meta = {"name": "mysnap", "version": "1", "kernel": "", "rootfs": ""}
        (snap_dir / "meta.json").write_text(json.dumps(meta))

        class FakeStorage:
            def download(self, key): return b""

        dl = SnapshotDownloader(FakeStorage(), str(tmp_path))
        paths = dl.ensure("mysnap")

        assert paths is not None
        span_names = [s[0] for s in spans_started]
        assert "vm.restore_snapshot" in span_names

    def test_ensure_span_has_snapshot_name_attribute(self, monkeypatch, tmp_path):
        """Span vm.restore_snapshot harus punya attribute snapshot_name."""
        import json
        from orchestrator.snapshot import SnapshotDownloader

        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append((name, attrs or {}))
                yield _NoopSpan()

        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: RecordingTracer())

        snap_dir = tmp_path / "mysnap"
        snap_dir.mkdir()
        (snap_dir / "vmstate.bin").write_bytes(b"state")
        (snap_dir / "memory.bin").write_bytes(b"mem")
        meta = {"name": "mysnap", "version": "1", "kernel": "", "rootfs": ""}
        (snap_dir / "meta.json").write_text(json.dumps(meta))

        class FakeStorage:
            def download(self, key): return b""

        dl = SnapshotDownloader(FakeStorage(), str(tmp_path))
        dl.ensure("mysnap")

        snap_span = next(s for s in spans_started if s[0] == "vm.restore_snapshot")
        assert snap_span[1].get("snapshot_name") == "mysnap"
```

- [ ] **Step 2: Jalankan test — pastikan FAIL**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/test_snapshot_spans.py -v
```

Expected: FAIL — span `vm.restore_snapshot` belum ada.

- [ ] **Step 3: Tambah span ke `SnapshotDownloader.ensure()`**

Di `sandbox-worker/src/orchestrator/snapshot.py`, tambahkan import dan wrap `ensure()`:

```python
import time   # tambahkan import ini (sudah ada atau tambahkan)
from adapters.tracing import get_tracer   # tambahkan import ini

class SnapshotDownloader:
    # ... (tidak ada perubahan di __init__, upload, _load_meta, _all_exist)

    def ensure(self, name: str) -> SnapshotPaths:
        """Return local paths for the named snapshot, downloading if needed."""
        tracer = get_tracer()
        start = time.monotonic()
        with tracer.start_span("vm.restore_snapshot", {"snapshot_name": name}) as span:
            local_dir = os.path.join(self._cache_dir, name)
            paths = SnapshotPaths(
                state_file=os.path.join(local_dir, "vmstate.bin"),
                mem_file=os.path.join(local_dir, "memory.bin"),
                meta_file=os.path.join(local_dir, "meta.json"),
            )

            if self._all_exist(paths.state_file, paths.mem_file, paths.meta_file):
                log.debug("snapshot cache hit", name=name)
                result = self._load_meta(paths)
                span.set_attribute("cache_hit", True)
                span.set_attribute("duration_ms", int((time.monotonic() - start) * 1000))
                return result

            log.info("snapshot not cached, downloading via BlobStore", name=name)
            Path(local_dir).mkdir(parents=True, exist_ok=True)

            for blob in self._BLOBS:
                key = f"{name}/{blob}"
                dest = os.path.join(local_dir, blob)
                data = self._storage.download(key)
                Path(dest).write_bytes(data)
                log.debug("snapshot blob downloaded", key=key, dest=dest)

            span.set_attribute("cache_hit", False)
            span.set_attribute("duration_ms", int((time.monotonic() - start) * 1000))
            return self._load_meta(paths)
```

- [ ] **Step 4: Jalankan test — pastikan PASS**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/test_snapshot_spans.py -v
```

Expected: 2 tests PASSED.

- [ ] **Step 5: Jalankan seluruh unit tests — pastikan tidak ada regresi**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/ -v --tb=short
```

Expected: semua tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sandbox-worker/src/orchestrator/snapshot.py \
        sandbox-worker/tests/unit/test_snapshot_spans.py
git commit -m "feat(tracing): add vm.restore_snapshot OTEL span to SnapshotDownloader"
```

---

## Task 10: Tambah `ruff` dan `mypy` ke dev deps

**Files:**
- Modify: `sandbox-worker/pyproject.toml`

- [ ] **Step 1: Tambah `ruff` dan `mypy` ke `[dev]` optional dependencies**

Di `sandbox-worker/pyproject.toml`, ubah bagian `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]
```

- [ ] **Step 2: Re-install deps**

```bash
cd sandbox-worker && uv pip install -e ".[dev]"
```

Expected: ruff dan mypy ter-install tanpa error.

- [ ] **Step 3: Jalankan lint**

```bash
cd sandbox-worker && .venv/bin/ruff check src/ --select=E,F,I
```

Expected: tidak ada error (atau list error yang bisa di-fix).

- [ ] **Step 4: Commit**

```bash
git add sandbox-worker/pyproject.toml
git commit -m "fix(deps): add ruff and mypy to dev dependencies"
```

---

## Task 11: Verifikasi end-to-end

- [ ] **Step 1: Start semua services**

```bash
make services-up
```

Expected: postgres, redis, minio, consul, jaeger semua running.

- [ ] **Step 2: Start worker dengan DEV_MODE**

```bash
cd sandbox-worker && DEV_MODE=true OTEL_ENABLED=true .venv/bin/platform-api
```

Expected: log human-readable di terminal, bukan JSON wall.

- [ ] **Step 3: Kirim request dan perhatikan log**

Di terminal lain:
```bash
curl -sf -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{"tool":"echo","input":{"msg":"trace-test"}}' | python3 -m json.tool
```

Expected: response JSON dengan `status: completed`. Di log terminal worker, terlihat baris dengan `request_id=<8char>`.

- [ ] **Step 4: Lihat X-Request-ID di response header**

```bash
curl -si -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{"tool":"echo","input":{"msg":"hi"}}' | grep -i x-request-id
```

Expected: `x-request-id: abc12345`

- [ ] **Step 5: Buka Jaeger UI**

Buka `http://localhost:16686` di browser.
- Pilih service: `sandbox-platform`
- Klik **Find Traces**
- Expected: traces muncul dengan spans `pool.acquire` dan `vm.restore_snapshot`

- [ ] **Step 6: Search by request_id di Jaeger**

Di Jaeger UI → **Search** → Tags: `request_id=<id-dari-step-4>`
Expected: trace untuk request itu muncul dengan seluruh span tree.

- [ ] **Step 7: Jalankan seluruh unit tests sekali lagi**

```bash
cd sandbox-worker && .venv/bin/pytest tests/unit/ -v
```

Expected: semua tests PASS.

- [ ] **Step 8: Commit final**

```bash
git add -A
git commit -m "feat(dx+observability): complete DX setup and Jaeger tracing implementation"
```

---

## Ringkasan Perubahan

| Area | Sebelum | Sesudah |
|---|---|---|
| Setup dev baru | Manual, tebak env vars | `make setup` — satu perintah |
| Services | Satu flat compose | Terpisah: data/controller/monitoring |
| Tracing | HTTP middleware saja | pool.acquire + vm.restore_snapshot spans di Jaeger |
| Request ID | Tidak ada | X-Request-ID di setiap response header + semua log |
| Log dev mode | JSON wall | Human-readable dengan warna |
| Lint tools | Tidak ada di deps | `ruff` + `mypy` di `[dev]` |
