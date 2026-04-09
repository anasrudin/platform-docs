# Design: Developer Experience & Observability

| Field       | Value                                      |
|-------------|--------------------------------------------|
| Date        | 2026-04-10                                 |
| Status      | Draft — pending implementation plan        |
| Pain points | Setup baru ribet, logging/tracing tidak bisa trace request end-to-end |
| Scope       | `services/`, `sandbox-worker/src/`, `sandbox-worker/Makefile` |

## Problem

Dua pain point utama yang menjadi dasar design ini:

1. **Setup baru ribet** — tidak ada satu perintah untuk setup dev environment. Env vars tidak terdokumentasi, developer baru harus tebak-tebak variabel mana yang wajib.

2. **Logging/tracing membingungkan** — ketika request VM pool masuk, tidak bisa dijawab: masuk ke LB node mana, pool slot berapa, apakah masuk antrian Redis, ID log yang mana. Debugging berakhir dengan restart semua service.

## Goals

- Developer baru bisa setup dan jalankan platform dengan satu perintah
- Setiap request bisa di-trace dari masuk HTTP sampai VM execute, termasuk pool slot dan Redis job ID
- Log di dev mode human-readable, tidak JSON wall
- Jaeger UI bisa digunakan untuk search trace by `request_id`

## Non-goals

- Prometheus metrics dan Grafana dashboard (next iteration)
- Production-grade Jaeger storage backend (Cassandra/Elasticsearch) — ini hanya dev setup
- Alert rules dan SLO monitoring

---

## Design

### 1. Reorganisasi `services/`

**Sebelum:**
```
services/
  docker-compose.yml    # flat — semua service dalam satu file
  haproxy/
  minio/
  nomad/
  scripts/
  systemd/
```

**Sesudah:**
```
services/
  data/
    docker-compose.yml          # postgres, redis, minio
  controller/
    docker-compose.yml          # consul, haproxy
  monitoring/
    docker-compose.yml          # jaeger (sekarang), prometheus+grafana (nanti)
    jaeger/
      config.yaml               # sampling rate, retention
  docker-compose.yml            # root — include semua via Docker Compose include
  haproxy/
  minio/
  nomad/
  scripts/
  systemd/
```

**Root compose** menggunakan Docker Compose `include` directive (Compose v2.20+):

```yaml
# services/docker-compose.yml
include:
  - data/docker-compose.yml
  - controller/docker-compose.yml
  - monitoring/docker-compose.yml

networks:
  platform-net:
    driver: bridge
```

Setiap sub-compose menggunakan network `platform-net` yang sama sehingga service bisa saling reach.

**Makefile targets baru (root Makefile):**

```makefile
services-data:
    cd services && docker compose -f data/docker-compose.yml up -d

services-controller:
    cd services && docker compose -f controller/docker-compose.yml up -d

services-monitoring:
    cd services && docker compose -f monitoring/docker-compose.yml up -d

services-up:
    cd services && docker compose up -d
```

### 2. Jaeger di `services/monitoring/`

```yaml
# services/monitoring/docker-compose.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.57
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    ports:
      - "16686:16686"   # Jaeger UI
      - "4317:4317"     # OTEL gRPC collector
      - "4318:4318"     # OTEL HTTP collector
    networks:
      - platform-net
    volumes:
      - ./jaeger/config.yaml:/etc/jaeger/config.yaml

networks:
  platform-net:
    external: true
```

Jaeger `all-in-one` menyimpan trace di memory — cukup untuk dev, zero external dependency.

**Env var yang perlu ditambah ke `.env.example`:**
```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=sandbox-platform
```

### 3. Setup DX — `.env.example` dan `make setup`

**`.env.example`** dibuat dari semua variabel di `config/settings.py`, dibagi per section dengan komentar:

```bash
# ── API ───────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8080
DEV_MODE=true          # true = human-readable logs + /debug/state endpoint

# ── Firecracker ───────────────────────────────────
FC_MODE=sim            # sim = aman untuk macOS, real = butuh /dev/kvm
FC_POOL_SIZE=2
FC_DEV_MODE=true

# ── Redis ─────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── MinIO ─────────────────────────────────────────
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=platform-artifacts

# ── Observability ─────────────────────────────────
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=sandbox-platform

# ── Feature flags (default off) ───────────────────
CONSUL_ENABLED=false
SCALER_ENABLED=false
MTLS_ENABLED=false
```

**`make setup` target (root Makefile):**

```makefile
setup:
    @echo ">>> Copying .env.example → .env (jika belum ada)..."
    @[ -f .env ] || cp .env.example .env
    @echo ">>> Installing worker deps..."
    cd sandbox-worker && uv venv .venv && uv pip install -e ".[dev]"
    @echo ">>> Starting infra (data + monitoring)..."
    $(MAKE) services-data services-monitoring
    @echo ">>> Waiting for services..."
    @sleep 5
    @$(MAKE) services-status
    @echo ""
    @echo "Done. Jalankan: make worker-run"
```

### 4. OTEL Spans di Pool, Redis, dan VM

**Trace tree yang akan terbentuk:**

```
POST /execute  [span: http.request]
├── router.resolve_tier          attributes: tool, tier (wasm|microvm)
├── redis.enqueue_job            attributes: job_id, queue_depth, wait_ms
├── pool.acquire_slot            attributes: node_id, slot_index, pool_available
│   └── vm.restore_snapshot     attributes: snapshot_name, duration_ms
└── vm.execute                   attributes: tool, status, exit_code, duration_ms
```

**Implementasi di `orchestrator/lifecycle.py`:**

```python
from adapters.tracing import get_tracer

tracer = get_tracer(__name__)

class VMLifecycleManager:
    def acquire_slot(self, request_id: str) -> VMSlot:
        with tracer.start_as_current_span("pool.acquire_slot") as span:
            span.set_attribute("request_id", request_id)
            span.set_attribute("node_id", self.node_id)
            slot = self._pool.acquire()
            span.set_attribute("slot_index", slot.index)
            span.set_attribute("pool_available", self._pool.available)
            return slot
```

Pattern yang sama untuk `redis.enqueue_job` di `service/execution.py` dan `vm.restore_snapshot` di `orchestrator/snapshot.py`.

### 5. Request ID Middleware

File baru: `sandbox-worker/src/api/middleware/request_id.py`

```python
from uuid import uuid4
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())[:8]
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

Di-register di `api/app.py` sebelum middleware lain:

```python
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TracingMiddleware)
app.add_middleware(TenantAuthMiddleware, ...)
```

Hasilnya: `X-Request-ID` ada di response header, bisa di-copy langsung dari browser devtools atau curl output, lalu di-search di Jaeger UI.

### 6. Dev-mode Logging

```python
# api/app.py — lifespan, sebelum yield

if settings.api.dev_mode:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="%H:%M:%S.%f"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
else:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
```

Output dev mode:
```
10:23:45.123 [info     ] pool.acquire_slot  request_id=req-abc node=node-1 slot=2 pool_available=1
10:23:45.450 [info     ] redis.enqueue      request_id=req-abc job_id=job-xyz queue_depth=3
10:23:45.891 [info     ] vm.execute         request_id=req-abc tool=python_run status=completed duration_ms=441
```

---

## Alur Debug Setelah Implementasi

**Sebelum:** tidak tahu harus mulai dari mana → restart semua.

**Sesudah:**

1. Kirim request, lihat `X-Request-ID: req-abc` di response header
2. Buka terminal → `grep req-abc sandbox-worker.log` → lihat semua log untuk request itu
3. Buka `http://localhost:16686` → search by tag `request_id=req-abc` → lihat full trace: masuk node mana, pool slot berapa, Redis job ID apa, berapa lama tiap step

---

## File yang Akan Berubah

| File | Perubahan |
|---|---|
| `services/docker-compose.yml` | Refactor ke root compose dengan `include` |
| `services/data/docker-compose.yml` | Baru — postgres, redis, minio |
| `services/controller/docker-compose.yml` | Baru — consul, haproxy |
| `services/monitoring/docker-compose.yml` | Baru — jaeger |
| `services/monitoring/jaeger/config.yaml` | Baru — jaeger config |
| `.env.example` | Baru — semua vars dari settings.py |
| `Makefile` | Tambah `setup`, `services-data`, `services-controller`, `services-monitoring` |
| `sandbox-worker/src/api/middleware/request_id.py` | Baru — RequestIDMiddleware |
| `sandbox-worker/src/api/app.py` | Register RequestIDMiddleware, dev/prod log config |
| `sandbox-worker/src/orchestrator/lifecycle.py` | OTEL spans di pool.acquire_slot |
| `sandbox-worker/src/orchestrator/snapshot.py` | OTEL spans di vm.restore_snapshot |
| `sandbox-worker/src/service/execution.py` | OTEL spans di redis.enqueue_job |
| `sandbox-worker/src/adapters/tracing/otel.py` | Pastikan `get_tracer()` helper tersedia |
| `sandbox-worker/pyproject.toml` | Tambah `ruff`, `mypy` ke dev deps |
| `sandbox-worker/src/config/settings.py` | Tambah `dev_mode: bool` ke `APIConfig` (env var `DEV_MODE`) |
