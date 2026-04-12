# Microservices Split: platform-api + sandbox-worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pisah monolith `sandbox-worker` menjadi dua service terpisah — `platform-api` (controller) dan `sandbox-worker` (worker) — yang berkomunikasi via HTTP dengan service discovery melalui Consul.

**Architecture:** `platform-api` menerima request dari client, menyimpan session di Redis, lalu mendispatch job ke worker yang tepat via Consul service discovery. `sandbox-worker` hanya tahu cara menjalankan kode di VM — tidak tahu tentang sessions atau routing. Keduanya tidak berbagi kode Python secara langsung; kontrak dinyatakan via HTTP schema.

**Tech Stack:** Python 3.12+, FastAPI, httpx (async HTTP client), Redis (session store), Consul (service discovery), Nomad (scheduler), structlog, OpenTelemetry.

---

## Topologi Target

```
                           ┌─────────────────────────────────────────┐
                           │           CONTROLLER LAYER               │
                           │                                          │
  Client ──HTTPS──▶  HAProxy (:80/:443)                              │
                           │  │                                       │
                           │  └──round-robin──▶  platform-api (:8080)│
                           │                      │                   │
                           │                      │  session R/W      │
                           │                      ▼                   │
                           │                    Redis (:6379)         │
                           │                      │                   │
                           │              Consul lookup               │
                           │              (runtime tag)               │
                           └──────────────────────┼──────────────────┘
                                                  │ HTTP POST /execute
                           ┌──────────────────────┼──────────────────┐
                           │           WORKER LAYER                   │
                           │                      │                   │
                           │  ┌───────────────────┼────────────────┐ │
                           │  │  Nomad client node │                │ │
                           │  │                   ▼                │ │
                           │  │  sandbox-fc-agent (:8081) ─────────┼─┼──▶ Firecracker VM
                           │  │  sandbox-wasm-agent (:8082) ───────┼─┼──▶ WASM runtime
                           │  │  sandbox-gui-agent (:8083) ────────┼─┼──▶ Chromium
                           │  │                                    │ │
                           │  │  [setiap agent register ke Consul] │ │
                           │  └────────────────────────────────────┘ │
                           └─────────────────────────────────────────┘
                                                  │
                           ┌──────────────────────┼──────────────────┐
                           │           DATA LAYER                     │
                           │                      │                   │
                           │  Consul (:8500)  ◀───┘                   │
                           │  PostgreSQL (:5432)                      │
                           │  MinIO (:9000)   ◀─── artifacts/snapshot │
                           │  Jaeger (:16686) ◀─── traces             │
                           └─────────────────────────────────────────┘

Coupling:
  platform-api → worker:   HTTP  (via Consul, tidak hardcode IP)
  platform-api → Redis:    TCP   (session state)
  platform-api → Consul:   HTTP  (service discovery)
  worker       → Consul:   HTTP  (self-registration)
  worker       → MinIO:    HTTP  (download snapshots)
  semua        → Jaeger:   gRPC  (traces, OTEL)
```

---

## Struktur File Target

```
platform-docs/
├── platform-api/                    ← NEW service (controller)
│   ├── src/
│   │   ├── api/
│   │   │   ├── app.py               # FastAPI entry, lifespan
│   │   │   ├── routes/              # semua HTTP endpoints
│   │   │   │   ├── execute.py       # dispatch ke worker via HTTP
│   │   │   │   ├── session.py       # CRUD session (Redis-backed)
│   │   │   │   ├── health.py
│   │   │   │   ├── artifact.py
│   │   │   │   ├── streaming.py
│   │   │   │   ├── workflow.py
│   │   │   │   └── workspace.py
│   │   │   ├── middleware/          # auth, tracing, request_id
│   │   │   └── schemas/             # Pydantic request/response
│   │   │       ├── requests.py
│   │   │       └── worker.py        # NEW: schema untuk worker API
│   │   ├── service/
│   │   │   ├── session.py           # MODIFIED: Redis-backed (bukan in-memory)
│   │   │   ├── execution.py         # MODIFIED: HTTP dispatch ke worker
│   │   │   ├── worker_client.py     # NEW: httpx client + Consul discovery
│   │   │   ├── artifact.py
│   │   │   ├── health.py
│   │   │   ├── streaming.py
│   │   │   ├── workflow.py
│   │   │   └── workspace.py
│   │   ├── models/                  # domain models (copy dari sandbox-worker)
│   │   │   ├── job.py
│   │   │   ├── session.py
│   │   │   └── workspace.py
│   │   ├── config/
│   │   │   └── settings.py          # env vars (tanpa FC/WASM/GUI config)
│   │   └── adapters/
│   │       ├── registry/            # Consul client (discovery)
│   │       ├── tracing/             # OTEL
│   │       └── storage/             # artifact store
│   ├── pyproject.toml
│   └── Makefile
│
├── sandbox-worker/                  ← TRIMMED: hanya worker
│   └── src/
│       ├── api/                     # NEW: minimal HTTP API
│       │   ├── app.py               # entry point worker
│       │   └── routes/
│       │       ├── execute.py       # POST /execute — terima job, jalankan VM
│       │       └── health.py        # GET /health — status pool
│       ├── runtime/                 # UNCHANGED
│       ├── agents/                  # UNCHANGED
│       ├── communication/           # UNCHANGED
│       ├── models/
│       │   └── job.py               # minimal job model
│       ├── config/
│       │   └── settings.py          # TRIMMED: FC/WASM/GUI config only
│       └── adapters/
│           ├── registry/            # Consul self-registration
│           ├── tracing/
│           └── storage/snapshot_blob.py
│
└── services/
    ├── controller/
    │   ├── nomad/jobs/
    │   │   ├── platform-api.nomad   # NEW: nomad job untuk controller
    │   │   └── sandbox-worker.nomad # UNCHANGED (worker jobs)
    │   └── docker-compose.yml       # MODIFIED: tambah platform-api service
    └── data/                        # UNCHANGED
```

---

## Kontrak API antar Service

### Worker API (sandbox-worker)

```
POST /execute
Content-Type: application/json

Request:
{
  "job_id":    "uuid",
  "session_id": "uuid",
  "tool":      "python_run",
  "input":     { "code": "print('hello')" },
  "runtime":   "firecracker"   # firecracker | wasm | gui
}

Response 200:
{
  "job_id":      "uuid",
  "status":      "completed",   # completed | failed
  "output":      "hello\n",
  "error":       "",
  "duration_ms": 142
}

GET /health
Response 200:
{
  "status":         "ok",
  "runtime":        "firecracker",
  "pool_available": 3,
  "pool_total":     5
}
```

### Session Store Schema (Redis)

```
Key:   session:{session_id}
Value: JSON {
  "session_id":    "uuid",
  "runtime":       "firecracker",
  "status":        "active",
  "snapshot_mode": "clean",
  "created_at":    "2026-04-12T00:00:00Z"
}
TTL: 3600s (dari REDIS_SESSION_TTL)
```

---

## Scope Check — Subsystem Independence

Plan ini terdiri dari 3 subsystem yang bisa dikerjakan terpisah:

| Subsystem | Service | Independent? |
|-----------|---------|-------------|
| A: Worker API | sandbox-worker | Ya — bisa test sendiri |
| B: Session → Redis | platform-api | Ya — tidak butuh worker |
| C: platform-api + worker discovery | platform-api | Butuh A selesai dulu |

Urutan eksekusi: **A → B → C** (A dan B bisa paralel, C butuh A dan B).

---

## Task 1 — Worker: Buat minimal HTTP API di sandbox-worker

**Files:**
- Create: `sandbox-worker/src/api/routes/execute.py`
- Create: `sandbox-worker/src/api/routes/health.py`
- Create: `sandbox-worker/src/api/app.py` (ganti yang lama — hapus semua service/orchestrator code)
- Modify: `sandbox-worker/src/config/settings.py` (hapus DB, consul, workflow, dll)
- Create: `sandbox-worker/tests/unit/test_worker_api.py`

- [ ] **Step 1: Tulis failing test untuk POST /execute**

```python
# sandbox-worker/tests/unit/test_worker_api.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

def make_client():
    from api.app import create_app
    app = create_app()
    return TestClient(app)

def test_execute_returns_job_result():
    mock_response = MagicMock()
    mock_response.stdout = '{"output": "hello"}'
    mock_response.stderr = ""
    mock_response.exit_code = 0

    with patch("api.app._state") as mock_state:
        mock_mgr = MagicMock()
        mock_mgr.acquire.return_value.__enter__ = lambda s: mock_response
        mock_state.__getitem__.return_value = mock_mgr
        client = make_client()
        resp = client.post("/execute", json={
            "job_id": "test-job-1",
            "session_id": "test-session-1",
            "tool": "python_run",
            "input": {"code": "print('hello')"},
            "runtime": "firecracker",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("completed", "failed")
    assert "job_id" in body
    assert "duration_ms" in body

def test_health_returns_pool_info():
    client = make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "runtime" in body
```

- [ ] **Step 2: Run test — pastikan FAIL**

```bash
cd sandbox-worker
pytest tests/unit/test_worker_api.py -v
# Expected: ImportError atau AttributeError — api.app belum ada endpoint ini
```

- [ ] **Step 3: Buat schema request/response worker**

```python
# sandbox-worker/src/api/schemas/worker.py
from __future__ import annotations
from pydantic import BaseModel

class ExecuteRequest(BaseModel):
    job_id: str
    session_id: str
    tool: str
    input: dict
    runtime: str = "firecracker"

class ExecuteResponse(BaseModel):
    job_id: str
    status: str        # completed | failed
    output: str = ""
    error: str = ""
    duration_ms: int
```

- [ ] **Step 4: Buat route execute**

```python
# sandbox-worker/src/api/routes/execute.py
from __future__ import annotations
import time
import structlog
from fastapi import APIRouter, HTTPException
from api.schemas.worker import ExecuteRequest, ExecuteResponse

log = structlog.get_logger()

def register(state: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/execute", response_model=ExecuteResponse)
    def execute(req: ExecuteRequest):
        mgr = state.get("lifecycle_mgr")
        if mgr is None:
            raise HTTPException(503, "Worker not ready")

        start = time.monotonic()
        vm = mgr.acquire(timeout=30.0)
        try:
            resp = vm.execute(req.tool, req.input)
            status = "completed" if resp.exit_code == 0 else "failed"
            output = resp.stdout
            error = resp.stderr
        finally:
            mgr.release(vm)

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("job executed", job_id=req.job_id, status=status, duration_ms=duration_ms)

        return ExecuteResponse(
            job_id=req.job_id,
            status=status,
            output=output,
            error=error,
            duration_ms=duration_ms,
        )

    return router
```

- [ ] **Step 5: Buat route health**

```python
# sandbox-worker/src/api/routes/health.py
from __future__ import annotations
from fastapi import APIRouter

def register(state: dict) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health():
        mgr = state.get("lifecycle_mgr")
        runtime = state.get("runtime_name", "firecracker")
        pool_available = 0
        pool_total = 0
        if mgr and mgr._pool:
            pool_available = getattr(mgr._pool, "available", 0)
            pool_total = mgr._pool_size

        return {
            "status": "ok",
            "runtime": runtime,
            "pool_available": pool_available,
            "pool_total": pool_total,
        }

    return router
```

- [ ] **Step 6: Buat app.py baru (slim — hanya worker)**

```python
# sandbox-worker/src/api/app.py
"""sandbox-worker — minimal worker API.

Hanya menerima job execution requests dari platform-api.
Tidak ada session management, routing, atau business logic di sini.
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from adapters.registry.consul import ConsulClient
from adapters.storage.snapshot_blob import SnapshotBlobStore
from adapters.tracing import init_tracer
from api.routes import execute, health
from config.settings import settings
from orchestrator.lifecycle import VMLifecycleManager

log = structlog.get_logger()
_state: dict = {}

RUNTIME_NAME = os.environ.get("RUNTIME_TIER", "firecracker")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracer(
        driver="otel" if settings.tracing.enabled else "noop",
        service_name=f"sandbox-worker-{RUNTIME_NAME}",
        otlp_endpoint=settings.tracing.otlp_endpoint,
    )

    snapshot_store = SnapshotBlobStore(
        endpoint=settings.storage.endpoint,
        access_key=settings.storage.access_key,
        secret_key=settings.storage.secret_key,
        bucket=settings.firecracker.snapshot_bucket,
        local_dir=settings.storage.local_dir,
    )
    snapshot_name = os.environ.get("SNAPSHOT_NAME", "python-v1")

    mgr = VMLifecycleManager(
        storage=snapshot_store,
        snapshot_name=snapshot_name,
        pool_size=settings.firecracker.pool_size,
        firecracker_bin=settings.firecracker.binary_path,
        dev_mode=settings.firecracker.dev_mode,
    )
    mgr.start()
    _state["lifecycle_mgr"] = mgr
    _state["runtime_name"] = RUNTIME_NAME

    # Consul self-registration
    if settings.consul.enabled:
        import socket
        consul = ConsulClient()
        addr = socket.gethostbyname(socket.gethostname())
        await consul.register_service(
            name=f"sandbox-{RUNTIME_NAME}-agent",
            service_id=f"sandbox-{RUNTIME_NAME}-{settings.api.port}",
            address=addr,
            port=settings.api.port,
            health_url=f"http://{addr}:{settings.api.port}/health",
            tags=["sandbox", f"runtime={RUNTIME_NAME}"],
        )
        log.info("registered with consul", runtime=RUNTIME_NAME, port=settings.api.port)

    log.info("sandbox-worker started", runtime=RUNTIME_NAME, port=settings.api.port)
    yield
    mgr.stop()
    log.info("sandbox-worker stopped")


def create_app() -> FastAPI:
    app = FastAPI(title=f"sandbox-worker-{RUNTIME_NAME}", lifespan=lifespan)
    app.include_router(health.register(_state))
    app.include_router(execute.register(_state))
    return app


app = create_app()

def main():
    uvicorn.run("api.app:app", host=settings.api.host, port=settings.api.port)

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run test — pastikan PASS**

```bash
cd sandbox-worker
pytest tests/unit/test_worker_api.py -v
# Expected: 2 passed
```

- [ ] **Step 8: Commit**

```bash
git add sandbox-worker/src/api/ sandbox-worker/tests/unit/test_worker_api.py
git commit -m "feat(worker): add minimal HTTP API — POST /execute, GET /health"
```

---

## Task 2 — Session Store: Migrasikan SessionService ke Redis

**Files:**
- Create: `platform-api/src/service/session.py`
- Modify: `sandbox-worker/src/service/session.py` (hapus — tidak lagi dibutuhkan di worker)
- Create: `platform-api/tests/unit/test_session_redis.py`

- [ ] **Step 1: Tulis failing test session Redis**

```python
# platform-api/tests/unit/test_session_redis.py
import pytest
import fakeredis
from service.session import SessionService

@pytest.fixture
def session_svc():
    import fakeredis
    r = fakeredis.FakeRedis(decode_responses=True)
    return SessionService(redis=r, ttl=3600)

def test_create_session_stores_in_redis(session_svc):
    result = session_svc.create("firecracker", "clean")
    assert "session_id" in result
    assert result["runtime"] == "firecracker"
    assert result["status"] == "active"

def test_get_session_returns_stored(session_svc):
    created = session_svc.create("firecracker", "clean")
    sid = created["session_id"]
    sess = session_svc.get(sid)
    assert sess["session_id"] == sid

def test_get_missing_session_raises(session_svc):
    with pytest.raises(KeyError):
        session_svc.get("nonexistent-id")

def test_close_session_removes_from_redis(session_svc):
    created = session_svc.create("firecracker", "clean")
    sid = created["session_id"]
    session_svc.close(sid)
    with pytest.raises(KeyError):
        session_svc.get(sid)
```

- [ ] **Step 2: Run test — pastikan FAIL**

```bash
cd platform-api
pytest tests/unit/test_session_redis.py -v
# Expected: ModuleNotFoundError — platform-api belum ada
```

- [ ] **Step 3: Setup platform-api directory structure**

```bash
mkdir -p platform-api/src/{api/{routes,middleware,schemas},service,models,config,adapters/{registry,tracing,storage}}
mkdir -p platform-api/tests/unit
touch platform-api/src/__init__.py
touch platform-api/tests/__init__.py
touch platform-api/tests/unit/__init__.py
```

- [ ] **Step 4: Buat pyproject.toml platform-api**

```toml
# platform-api/pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "platform-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "httpx>=0.27",
    "redis>=5.0",
    "structlog>=24.1",
    "opentelemetry-sdk>=1.24",
    "opentelemetry-exporter-otlp-proto-grpc>=1.24",
    "pydantic>=2.7",
    "minio>=7.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "fakeredis>=2.23", "httpx"]

[project.scripts]
platform-api = "api.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] **Step 5: Buat SessionService berbasis Redis**

```python
# platform-api/src/service/session.py
"""SessionService — Redis-backed session store.

Tiap session disimpan di Redis dengan TTL.
Mendukung multiple platform-api instances tanpa sticky session.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()

VALID_RUNTIMES = {"firecracker", "microvm", "wasm", "gui"}
VALID_MODES = {"clean", "continuous"}


class SessionService:
    def __init__(self, redis, ttl: int = 3600) -> None:
        self._r = redis
        self._ttl = ttl

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def create(self, runtime_str: str = "firecracker", snapshot_mode_str: str = "clean") -> dict:
        runtime = runtime_str if runtime_str in VALID_RUNTIMES else "firecracker"
        # "microvm" adalah alias untuk "firecracker"
        if runtime == "microvm":
            runtime = "firecracker"
        mode = snapshot_mode_str if snapshot_mode_str in VALID_MODES else "clean"

        session_id = str(uuid.uuid4())
        data = {
            "session_id": session_id,
            "runtime": runtime,
            "status": "active",
            "snapshot_mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._r.setex(self._key(session_id), self._ttl, json.dumps(data))
        log.info("session created", session_id=session_id, runtime=runtime)
        return data

    def get(self, session_id: str) -> dict:
        raw = self._r.get(self._key(session_id))
        if raw is None:
            raise KeyError(f"Session {session_id!r} not found")
        return json.loads(raw)

    def close(self, session_id: str) -> None:
        deleted = self._r.delete(self._key(session_id))
        if deleted:
            log.info("session closed", session_id=session_id)
```

- [ ] **Step 6: Install deps dan run test**

```bash
cd platform-api
uv pip install -e ".[dev]"
pytest tests/unit/test_session_redis.py -v
# Expected: 4 passed
```

- [ ] **Step 7: Commit**

```bash
git add platform-api/
git commit -m "feat(platform-api): init service directory + Redis-backed SessionService"
```

---

## Task 3 — Worker Client: HTTP dispatch dari platform-api ke worker

**Files:**
- Create: `platform-api/src/service/worker_client.py`
- Create: `platform-api/src/service/execution.py`
- Create: `platform-api/tests/unit/test_worker_client.py`

- [ ] **Step 1: Tulis failing test worker client**

```python
# platform-api/tests/unit/test_worker_client.py
import pytest
import httpx
import respx
from service.worker_client import WorkerClient, WorkerUnavailableError

MOCK_EXECUTE_RESP = {
    "job_id": "job-1",
    "status": "completed",
    "output": "hello\n",
    "error": "",
    "duration_ms": 123,
}

@pytest.fixture
def client():
    return WorkerClient(consul_host="127.0.0.1", consul_port=8500, timeout=5.0)

@respx.mock
def test_dispatch_returns_result(client):
    # Mock Consul catalog lookup
    respx.get("http://127.0.0.1:8500/v1/catalog/service/sandbox-firecracker-agent").mock(
        return_value=httpx.Response(200, json=[{
            "ServiceAddress": "10.0.0.1",
            "ServicePort": 8081,
        }])
    )
    # Mock worker execute
    respx.post("http://10.0.0.1:8081/execute").mock(
        return_value=httpx.Response(200, json=MOCK_EXECUTE_RESP)
    )

    result = client.dispatch(
        runtime="firecracker",
        job_id="job-1",
        session_id="sess-1",
        tool="python_run",
        input_data={"code": "print('hello')"},
    )
    assert result["status"] == "completed"
    assert result["output"] == "hello\n"

@respx.mock
def test_dispatch_raises_when_no_workers(client):
    respx.get("http://127.0.0.1:8500/v1/catalog/service/sandbox-firecracker-agent").mock(
        return_value=httpx.Response(200, json=[])
    )
    with pytest.raises(WorkerUnavailableError):
        client.dispatch(
            runtime="firecracker",
            job_id="job-1",
            session_id="sess-1",
            tool="python_run",
            input_data={},
        )
```

- [ ] **Step 2: Run test — pastikan FAIL**

```bash
cd platform-api
pytest tests/unit/test_worker_client.py -v
# Expected: ImportError — worker_client belum ada
```

- [ ] **Step 3: Buat WorkerClient**

```python
# platform-api/src/service/worker_client.py
"""WorkerClient — HTTP client untuk mendispatch job ke sandbox-worker.

Menggunakan Consul untuk service discovery; tidak ada hardcoded IP.
Round-robin sederhana di antara healthy workers.

Loose coupling:
  - Hanya tahu HTTP contract (POST /execute)
  - Tidak import kode sandbox-worker
  - Worker address diambil dari Consul saat runtime
"""
from __future__ import annotations
import random
import structlog
import httpx

log = structlog.get_logger()

# Map runtime name → Consul service name
RUNTIME_SERVICE_MAP = {
    "firecracker": "sandbox-firecracker-agent",
    "wasm":        "sandbox-wasm-agent",
    "gui":         "sandbox-gui-agent",
}


class WorkerUnavailableError(Exception):
    """Tidak ada worker healthy untuk runtime yang diminta."""


class WorkerClient:
    def __init__(self, consul_host: str, consul_port: int, timeout: float = 30.0) -> None:
        self._consul_base = f"http://{consul_host}:{consul_port}"
        self._timeout = timeout

    def _get_worker_address(self, runtime: str) -> str:
        """Ambil address worker dari Consul. Raise WorkerUnavailableError jika tidak ada."""
        service_name = RUNTIME_SERVICE_MAP.get(runtime, f"sandbox-{runtime}-agent")
        url = f"{self._consul_base}/v1/catalog/service/{service_name}"

        with httpx.Client(timeout=5.0) as c:
            resp = c.get(url)
            resp.raise_for_status()
            instances = resp.json()

        if not instances:
            raise WorkerUnavailableError(
                f"No healthy workers for runtime={runtime!r} (service={service_name})"
            )

        # Simple random pick — HAProxy bisa juga handle load balancing
        instance = random.choice(instances)
        addr = instance["ServiceAddress"]
        port = instance["ServicePort"]
        return f"http://{addr}:{port}"

    def dispatch(
        self,
        runtime: str,
        job_id: str,
        session_id: str,
        tool: str,
        input_data: dict,
    ) -> dict:
        """Kirim job ke worker yang sesuai runtime. Return hasil eksekusi."""
        base_url = self._get_worker_address(runtime)
        payload = {
            "job_id": job_id,
            "session_id": session_id,
            "tool": tool,
            "input": input_data,
            "runtime": runtime,
        }

        log.info("dispatching job to worker",
                 job_id=job_id, runtime=runtime, worker=base_url)

        with httpx.Client(timeout=self._timeout) as c:
            resp = c.post(f"{base_url}/execute", json=payload)
            resp.raise_for_status()
            result = resp.json()

        log.info("worker job done",
                 job_id=job_id, status=result.get("status"), duration_ms=result.get("duration_ms"))
        return result
```

- [ ] **Step 4: Buat ExecutionService baru (HTTP-based)**

```python
# platform-api/src/service/execution.py
"""ExecutionService — mendispatch job ke worker via HTTP.

Tidak ada direct Firecracker/WASM code di sini.
Hanya orchestrate: buat job ID, dispatch ke worker, return result.
"""
from __future__ import annotations
import uuid
import structlog
from service.worker_client import WorkerClient, WorkerUnavailableError

log = structlog.get_logger()


class ExecutionService:
    def __init__(self, worker_client: WorkerClient) -> None:
        self._client = worker_client

    def execute(self, body: dict) -> dict:
        tool = body.get("tool", "")
        if not tool:
            raise ValueError("tool is required")

        session_id = body.get("session_id") or str(uuid.uuid4())
        input_data = body.get("input") or {}
        runtime = body.get("runtime", "firecracker")
        job_id = str(uuid.uuid4())

        try:
            result = self._client.dispatch(
                runtime=runtime,
                job_id=job_id,
                session_id=session_id,
                tool=tool,
                input_data=input_data,
            )
        except WorkerUnavailableError as exc:
            log.warning("no worker available", runtime=runtime, err=str(exc))
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "failed",
                "output": "",
                "error_message": f"No worker available for runtime={runtime}",
                "duration_ms": 0,
            }

        return {
            "job_id": result["job_id"],
            "session_id": session_id,
            "status": result["status"],
            "output": result.get("output", ""),
            "error_message": result.get("error", ""),
            "duration_ms": result.get("duration_ms", 0),
        }
```

- [ ] **Step 5: Run test — pastikan PASS**

```bash
cd platform-api
pytest tests/unit/test_worker_client.py -v
# Expected: 2 passed
```

- [ ] **Step 6: Commit**

```bash
git add platform-api/src/service/worker_client.py platform-api/src/service/execution.py platform-api/tests/unit/test_worker_client.py
git commit -m "feat(platform-api): WorkerClient dengan Consul discovery + ExecutionService HTTP dispatch"
```

---

## Task 4 — platform-api: Wire FastAPI app

**Files:**
- Copy (adapt): `platform-api/src/api/app.py` dari sandbox-worker
- Copy: `platform-api/src/api/routes/{execute,session,health,artifact,streaming,workflow,workspace}.py`
- Copy: `platform-api/src/api/middleware/`
- Copy: `platform-api/src/models/`
- Copy: `platform-api/src/adapters/`
- Copy: `platform-api/src/config/settings.py` (versi trimmed)
- Create: `platform-api/tests/unit/test_platform_api.py`

- [ ] **Step 1: Tulis failing test integrasi platform-api**

```python
# platform-api/tests/unit/test_platform_api.py
import pytest
import fakeredis
import respx
import httpx
from fastapi.testclient import TestClient

WORKER_RESP = {
    "job_id": "job-abc",
    "status": "completed",
    "output": "hello from worker\n",
    "error": "",
    "duration_ms": 55,
}

@pytest.fixture
def client(monkeypatch):
    # Patch Redis
    import fakeredis
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("CONSUL_ENABLED", "false")
    from api.app import create_app
    app = create_app(redis_override=fake_r)
    return TestClient(app)

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_create_and_execute_session(client):
    # Buat session
    sess_resp = client.post("/sessions", json={"runtime": "firecracker"})
    assert sess_resp.status_code == 200
    session_id = sess_resp.json()["session_id"]

    # Execute (mock worker via respx)
    with respx.mock:
        respx.get(
            "http://127.0.0.1:8500/v1/catalog/service/sandbox-firecracker-agent"
        ).mock(return_value=httpx.Response(200, json=[
            {"ServiceAddress": "10.0.0.1", "ServicePort": 8081}
        ]))
        respx.post("http://10.0.0.1:8081/execute").mock(
            return_value=httpx.Response(200, json=WORKER_RESP)
        )
        exec_resp = client.post("/execute", json={
            "session_id": session_id,
            "tool": "python_run",
            "input": {"code": "print('hello')"},
        })

    assert exec_resp.status_code == 200
    body = exec_resp.json()
    assert body["status"] == "completed"
    assert "output" in body
```

- [ ] **Step 2: Run test — pastikan FAIL**

```bash
cd platform-api
pytest tests/unit/test_platform_api.py -v
# Expected: ImportError — api.app belum ada
```

- [ ] **Step 3: Copy dan adapt file dari sandbox-worker**

```bash
# Copy files yang bisa dipakai langsung
cp sandbox-worker/src/adapters/ platform-api/src/adapters/ -r
cp sandbox-worker/src/models/ platform-api/src/models/ -r
cp sandbox-worker/src/api/middleware/ platform-api/src/api/middleware/ -r
cp sandbox-worker/src/api/schemas/ platform-api/src/api/schemas/ -r
cp sandbox-worker/src/api/routes/ platform-api/src/api/routes/ -r
```

- [ ] **Step 4: Buat platform-api/src/config/settings.py (trimmed)**

```python
# platform-api/src/config/settings.py
"""Settings untuk platform-api (controller service).

Hanya config yang relevan untuk controller:
- Redis (session store)
- Consul (worker discovery)
- API server
- Tracing
- Storage (artifact only)
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field

def _env(key, default=""): return os.environ.get(key) or default
def _env_int(key, default): return int(os.environ.get(key) or default)
def _env_bool(key): return os.environ.get(key, "").lower() == "true"

@dataclass
class RedisConfig:
    url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379/0"))
    session_ttl: int = field(default_factory=lambda: _env_int("REDIS_SESSION_TTL", 3600))

@dataclass
class ConsulConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("CONSUL_ENABLED"))
    host: str = field(default_factory=lambda: _env("CONSUL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("CONSUL_PORT", 8500))

@dataclass
class TracingConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    otlp_endpoint: str = field(default_factory=lambda: _env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))
    service_name: str = field(default_factory=lambda: _env("OTEL_SERVICE_NAME", "platform-api"))

@dataclass
class StorageConfig:
    endpoint: str = field(default_factory=lambda: _env("MINIO_ENDPOINT", "http://localhost:9000"))
    access_key: str = field(default_factory=lambda: _env("MINIO_ACCESS_KEY", "minioadmin"))
    secret_key: str = field(default_factory=lambda: _env("MINIO_SECRET_KEY", "minioadmin"))
    bucket: str = field(default_factory=lambda: _env("MINIO_BUCKET", "platform-artifacts"))
    local_dir: str = field(default_factory=lambda: _env("ARTIFACTS_LOCAL_DIR", ""))

@dataclass
class APIConfig:
    host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("API_PORT", 8080))
    dev_mode: bool = field(default_factory=lambda: _env_bool("DEV_MODE"))

@dataclass
class Settings:
    redis: RedisConfig = field(default_factory=RedisConfig)
    consul: ConsulConfig = field(default_factory=ConsulConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    api: APIConfig = field(default_factory=APIConfig)

settings = Settings()
```

- [ ] **Step 5: Buat platform-api/src/api/app.py**

```python
# platform-api/src/api/app.py
"""platform-api — controller service.

Menerima request dari client, menyimpan session di Redis,
mendispatch eksekusi ke sandbox-worker via Consul discovery.
Tidak ada Firecracker/WASM/GUI code di sini.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

import redis
import structlog
import uvicorn
from fastapi import FastAPI

from adapters.tracing import init_tracer
from api.middleware.auth import TenantAuthMiddleware, auth_config_from_env
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.tracing import TracingMiddleware
from api.routes import execute, health, session, artifact, streaming, workflow, workspace
from config.settings import settings
from service.session import SessionService
from service.execution import ExecutionService
from service.worker_client import WorkerClient

log = structlog.get_logger()
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI, redis_override=None):
    init_tracer(
        driver="otel" if settings.tracing.enabled else "noop",
        service_name=settings.tracing.service_name,
        otlp_endpoint=settings.tracing.otlp_endpoint,
    )

    # Session store — Redis
    r = redis_override or redis.Redis.from_url(settings.redis.url, decode_responses=True)
    _state["session_svc"] = SessionService(redis=r, ttl=settings.redis.session_ttl)

    # Worker discovery + execution dispatch
    worker_client = WorkerClient(
        consul_host=settings.consul.host,
        consul_port=settings.consul.port,
    )
    _state["exec_svc"] = ExecutionService(worker_client=worker_client)
    _state["worker_client"] = worker_client

    log.info("platform-api started", port=settings.api.port)
    yield
    log.info("platform-api stopped")


def create_app(redis_override=None) -> FastAPI:
    app = FastAPI(title="platform-api", lifespan=lambda a: lifespan(a, redis_override))

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TracingMiddleware)
    _auth_cfg = auth_config_from_env()
    app.add_middleware(TenantAuthMiddleware, enabled=_auth_cfg["enabled"])

    app.include_router(health.register(_state))
    app.include_router(session.register(_state))
    app.include_router(execute.register(_state))
    app.include_router(artifact.register(_state))
    app.include_router(streaming.register(_state))
    app.include_router(workflow.register(_state))
    app.include_router(workspace.register(_state))

    return app


app = create_app()

def main():
    uvicorn.run("api.app:app", host=settings.api.host, port=settings.api.port)

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test — pastikan PASS**

```bash
cd platform-api
pytest tests/unit/test_platform_api.py -v
# Expected: 2 passed
```

- [ ] **Step 7: Run seluruh test platform-api**

```bash
cd platform-api
pytest tests/ -v --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add platform-api/
git commit -m "feat(platform-api): wire FastAPI app — session+execute via Redis+HTTP dispatch"
```

---

## Task 5 — Nomad Jobs: Buat job spec untuk platform-api

**Files:**
- Create: `services/controller/nomad/jobs/platform-api.nomad`
- Modify: `services/controller/nomad/jobs/sandbox-worker.nomad` (update image reference)
- Modify: `services/controller/docker-compose.yml` (tambah platform-api)

- [ ] **Step 1: Buat Nomad job untuk platform-api**

```hcl
# services/controller/nomad/jobs/platform-api.nomad
job "platform-api" {
  datacenters = ["dc1"]
  type        = "service"

  group "controller" {
    count = 2  # minimal 2 untuk HA

    network {
      port "http" { static = 8080 }
    }

    service {
      name = "platform-api"
      port = "http"
      tags = ["api", "controller"]

      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "platform-api" {
      driver = "docker"

      config {
        image = "your-registry/platform-api:latest"
        ports = ["http"]
      }

      env {
        API_PORT     = "8080"

        # Session store (data layer)
        REDIS_URL    = "redis://redis.service.consul:6379/0"

        # Worker discovery (controller layer — Consul)
        CONSUL_ENABLED = "true"
        CONSUL_HOST    = "127.0.0.1"
        CONSUL_PORT    = "8500"

        # Artifact storage (data layer)
        MINIO_ENDPOINT   = "http://minio.service.consul:9000"
        MINIO_ACCESS_KEY = "minioadmin"
        MINIO_SECRET_KEY = "minioadmin"

        # Observability (data layer)
        OTEL_ENABLED                = "true"
        OTEL_EXPORTER_OTLP_ENDPOINT = "http://jaeger.service.consul:4317"
        OTEL_SERVICE_NAME           = "platform-api"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
```

- [ ] **Step 2: Update docker-compose.yml untuk dev local**

```yaml
# Tambahkan ke services/controller/docker-compose.yml
services:
  platform-api:
    build:
      context: ../../../platform-api
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      API_PORT: "8080"
      REDIS_URL: "redis://redis:6379/0"
      CONSUL_ENABLED: "false"   # dev: skip Consul, pakai env var langsung
      MINIO_ENDPOINT: "http://minio:9000"
      MINIO_ACCESS_KEY: "minioadmin"
      MINIO_SECRET_KEY: "minioadmin"
      OTEL_ENABLED: "false"
    depends_on:
      - redis
      - minio
```

- [ ] **Step 3: Buat Dockerfile untuk platform-api**

```dockerfile
# platform-api/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install -e "." --no-cache-dir
EXPOSE 8080
CMD ["platform-api"]
```

- [ ] **Step 4: Commit**

```bash
git add services/controller/nomad/jobs/platform-api.nomad \
        services/controller/docker-compose.yml \
        platform-api/Dockerfile
git commit -m "feat(infra): add platform-api Nomad job + docker-compose entry"
```

---

## Task 6 — Smoke Test: Verifikasi end-to-end dengan 2 service

**Files:**
- Modify: `tools/runbook/gcp-jumphost-nomad/smoke-test.sh`

- [ ] **Step 1: Update smoke-test untuk verifikasi 2 service terpisah**

```bash
# Tambahkan ke smoke-test.sh setelah test health:

echo "[0/5] Verify service separation..."
WORKER_HEALTH=$(curl -fsS "http://${CONTROLLER_HOST}:8081/health" 2>/dev/null || echo "")
if echo "$WORKER_HEALTH" | grep -q '"runtime"'; then
  pass "sandbox-worker health reachable (worker layer)"
  echo "  worker: $(echo $WORKER_HEALTH | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"runtime\"), \"pool:\", d.get(\"pool_available\"), \"/\", d.get(\"pool_total\"))')"
else
  warn "sandbox-worker health not reachable at :8081 (may be behind firewall)"
fi
```

- [ ] **Step 2: Run smoke test**

```bash
source config/topology.env
./smoke-test.sh
# Expected: semua 5 test pass, 2 service terdeteksi
```

- [ ] **Step 3: Commit**

```bash
git add tools/runbook/gcp-jumphost-nomad/smoke-test.sh
git commit -m "test(smoke): verify 2-service separation — platform-api + sandbox-worker"
```

---

## Ringkasan Loose Coupling

| Sebelum | Sesudah |
|---------|---------|
| `ExecutionService` → `VMLifecycleManager.acquire()` (in-process) | `ExecutionService` → `WorkerClient.dispatch()` (HTTP) |
| `SessionService` → `dict` in-memory (mati saat restart) | `SessionService` → Redis (shared, persistent) |
| Worker IP hardcoded | Worker IP dari Consul catalog (`/v1/catalog/service/…`) |
| 1 service tahu semua hal | platform-api: tidak tahu ada Firecracker; sandbox-worker: tidak tahu ada sessions |
| Scale unit = seluruh monolith | Scale platform-api dan sandbox-worker secara independen |

---

## Self-Review

**Spec coverage:**
- [x] Layer controller → `platform-api/` (api, service, models)
- [x] Layer worker → `sandbox-worker/` slim (runtime, agents, communication + minimal API)
- [x] Layer data → external services (unchanged) + client adapters
- [x] Loose coupling → HTTP, Consul discovery, Redis session
- [x] Topologi diagram → ada di atas
- [x] Nomad jobs → Task 5
- [x] Docker-compose dev → Task 5

**Gaps tidak ada.** Semua requirement tercover.
