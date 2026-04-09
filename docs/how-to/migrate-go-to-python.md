# Migrasi Go → Python: sandbox-platform

Panduan ini berisi perintah langkah demi langkah untuk memigrasikan seluruh codebase dari Go ke Python.
Semua perintah dijalankan dari direktori `sandbox-platform/`.

---

## Pemetaan Komponen

| Go | Python | Catatan |
|----|--------|---------|
| `go.mod` + `go.sum` | `pyproject.toml` + `requirements.txt` | |
| `pkg/types/types.go` | `sandbox_platform/types.py` | `dataclass` + `Enum` |
| `internal/queue/queue.go` | `sandbox_platform/queue/client.py` | `redis-py` |
| `internal/session/manager.go` | `sandbox_platform/session/manager.py` | `psycopg2` |
| `internal/router/router.go` | `sandbox_platform/router/router.py` | |
| `internal/router/rules.go` | `sandbox_platform/router/rules.py` | |
| `internal/artifacts/store.go` | `sandbox_platform/artifacts/store.py` | `minio` SDK |
| `runtime/firecracker/*.go` | `sandbox_platform/runtime/firecracker/*.py` | |
| `runtime/wasm/runtime.go` | `sandbox_platform/runtime/wasm/runtime.py` | |
| `runtime/gui/runtime.go` | `sandbox_platform/runtime/gui/runtime.py` | |
| `cmd/platform-api/main.go` | `cmd/platform_api.py` | FastAPI + uvicorn |
| `cmd/fc-agent/main.go` | `cmd/fc_agent.py` | |
| `cmd/wasm-agent/main.go` | `cmd/wasm_agent.py` | |
| `cmd/gui-agent/main.go` | `cmd/gui_agent.py` | |
| `github.com/google/uuid` | `uuid` | |
| `github.com/lib/pq` | `psycopg2-binary` | |
| `github.com/redis/go-redis/v9` | `redis` | |
| `net/http` | `fastapi` + `uvicorn` | |
| `log/slog` (JSON) | `structlog` | |
| `go build` | `uv pip install -e .` | |
| `go test ./...` | `pytest` | |

---

## Langkah 1 — Buat Struktur Direktori Python

```bash
cd sandbox-platform

# Buat struktur package Python
mkdir -p sandbox_platform/queue
mkdir -p sandbox_platform/session
mkdir -p sandbox_platform/router
mkdir -p sandbox_platform/artifacts
mkdir -p sandbox_platform/runtime/firecracker
mkdir -p sandbox_platform/runtime/wasm
mkdir -p sandbox_platform/runtime/gui
mkdir -p cmd
mkdir -p tests/unit
mkdir -p tests/integration

# Buat __init__.py untuk setiap package
touch sandbox_platform/__init__.py
touch sandbox_platform/queue/__init__.py
touch sandbox_platform/session/__init__.py
touch sandbox_platform/router/__init__.py
touch sandbox_platform/artifacts/__init__.py
touch sandbox_platform/runtime/__init__.py
touch sandbox_platform/runtime/firecracker/__init__.py
touch sandbox_platform/runtime/wasm/__init__.py
touch sandbox_platform/runtime/gui/__init__.py
```

---

## Langkah 2 — Setup Python Environment

```bash
# Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Verifikasi Python >= 3.12
python --version
```

---

## Langkah 3 — Buat pyproject.toml

```bash
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "sandbox-platform"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "redis>=5.2.0",
    "psycopg2-binary>=2.9.0",
    "minio>=7.2.0",
    "uuid>=1.30",
    "python-multipart>=0.0.12",
    "structlog>=24.4.0",
    "pydantic>=2.10.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "pytest-cov>=5.0.0",
]

[project.scripts]
platform-api  = "cmd.platform_api:main"
fc-agent      = "cmd.fc_agent:main"
wasm-agent    = "cmd.wasm_agent:main"
gui-agent     = "cmd.gui_agent:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["sandbox_platform*", "cmd*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
EOF
```

---

## Langkah 4 — Install Dependensi

```bash
uv pip install -e ".[dev]"

# Verifikasi semua package terinstall
pip list | grep -E "fastapi|redis|psycopg2|minio|structlog|pydantic|uvicorn"
```

---

## Langkah 5 — Migrasi File per File

Jalankan perintah berikut satu per satu, lalu isi file yang terbentuk dengan kode Python.

### 5.1 Types (`pkg/types/types.go` → `sandbox_platform/types.py`)

```bash
cat > sandbox_platform/types.py << 'EOF'
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Tier(str, Enum):
    WASM    = "wasm"
    MICROVM = "microvm"
    GUI     = "gui"


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


@dataclass
class Session:
    id: str
    runtime: Tier
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Job:
    id: str
    session_id: str
    tool: str
    tier: Tier
    input: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    output: str = ""
    error_msg: str = ""
    duration_ms: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RuntimeResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
EOF
```

### 5.2 Queue (`internal/queue/queue.go` → `sandbox_platform/queue/client.py`)

```bash
cat > sandbox_platform/queue/client.py << 'EOF'
import json
import time
from dataclasses import asdict

import redis as redis_lib

from sandbox_platform.types import Job, JobStatus, RuntimeResult, Tier


class QueueClient:
    def __init__(self, redis_client: redis_lib.Redis):
        self.rdb = redis_client

    def push_job(self, job: Job) -> None:
        data = json.dumps({
            "id": job.id,
            "session_id": job.session_id,
            "tool": job.tool,
            "tier": job.tier.value,
            "input": job.input,
            "status": job.status.value,
        })
        self.rdb.rpush(f"queue:{job.tier.value}", data)

    def pop_job(self, tier: Tier, timeout: int = 0) -> Job | None:
        result = self.rdb.blpop(f"queue:{tier.value}", timeout=timeout)
        if not result:
            return None
        _, raw = result
        data = json.loads(raw)
        return Job(
            id=data["id"],
            session_id=data["session_id"],
            tool=data["tool"],
            tier=Tier(data["tier"]),
            input=data.get("input", {}),
            status=JobStatus(data.get("status", "pending")),
        )

    def publish_result(self, job_id: str, result: RuntimeResult) -> None:
        key = f"result:{job_id}"
        data = json.dumps({"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code})
        self.rdb.rpush(key, data)
        self.rdb.expire(key, 300)  # 5 minutes TTL

    def wait_for_result(self, job_id: str, timeout: int = 30) -> RuntimeResult | None:
        key = f"result:{job_id}"
        result = self.rdb.brpop(key, timeout=timeout)
        if not result:
            return None
        _, raw = result
        data = json.loads(raw)
        return RuntimeResult(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", 0),
        )
EOF
```

### 5.3 Session Manager (`internal/session/manager.go` → `sandbox_platform/session/manager.py`)

```bash
cat > sandbox_platform/session/manager.py << 'EOF'
import json
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras

from sandbox_platform.types import Job, JobStatus, Session, Tier

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    runtime    TEXT NOT NULL DEFAULT 'wasm',
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    tool        TEXT NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'wasm',
    input       JSONB,
    status      TEXT NOT NULL DEFAULT 'pending',
    output      TEXT,
    error_msg   TEXT,
    duration_ms BIGINT DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
"""


class SessionManager:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    def init_db(self) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA)

    def create(self, runtime: Tier) -> Session:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, runtime, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                (session_id, runtime.value, "active", now, now),
            )
        return Session(id=session_id, runtime=runtime, status="active", created_at=now, updated_at=now)

    def get(self, session_id: str) -> Session:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        if not row:
            raise ValueError(f"session not found: {session_id}")
        return Session(
            id=row["id"], runtime=Tier(row["runtime"]),
            status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def create_job(self, session_id: str, tool: str, tier: Tier, input_data: dict) -> Job:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (id, session_id, tool, tier, input, status, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (job_id, session_id, tool, tier.value, json.dumps(input_data), JobStatus.PENDING.value, now, now),
            )
        return Job(id=job_id, session_id=session_id, tool=tool, tier=tier, input=input_data)

    def update_job(self, job_id: str, status: JobStatus, output: str, error_msg: str, duration_ms: int) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status=%s, output=%s, error_msg=%s, duration_ms=%s, updated_at=NOW() WHERE id=%s",
                (status.value, output, error_msg, duration_ms, job_id),
            )
EOF
```

### 5.4 Router (`internal/router/` → `sandbox_platform/router/`)

```bash
cat > sandbox_platform/router/rules.py << 'EOF'
from sandbox_platform.types import Tier

DEFAULT_RULES: dict[str, Tier] = {
    # WASM — cepat, stateless
    "html_parse":       Tier.WASM,
    "json_parse":       Tier.WASM,
    "markdown_convert": Tier.WASM,
    "docx_generate":    Tier.WASM,
    "echo":             Tier.WASM,
    "hello":            Tier.WASM,
    # MicroVM — I/O, network, subprocess
    "python_run":       Tier.MICROVM,
    "bash_run":         Tier.MICROVM,
    "git_clone":        Tier.MICROVM,
    "file_ops":         Tier.MICROVM,
    # GUI — butuh display
    "browser_open":     Tier.GUI,
    "web_scrape":       Tier.GUI,
    "excel_edit":       Tier.GUI,
    "office_automation":Tier.GUI,
}
EOF

cat > sandbox_platform/router/router.py << 'EOF'
import threading
import time

import structlog

from sandbox_platform.queue.client import QueueClient
from sandbox_platform.router.rules import DEFAULT_RULES
from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


class Router:
    def __init__(self, queue_client: QueueClient):
        self._rules: dict[str, Tier] = dict(DEFAULT_RULES)
        self._lock = threading.RLock()
        self.qc = queue_client

    def resolve(self, tool: str) -> Tier:
        with self._lock:
            return self._rules.get(tool, Tier.WASM)

    def register(self, tool: str, tier: Tier) -> None:
        with self._lock:
            self._rules[tool] = tier

    def execute(self, job: Job, timeout: int = 30) -> RuntimeResult:
        job.tier = self.resolve(job.tool)
        log.info("routing execution", tool=job.tool, tier=job.tier.value, job_id=job.id)

        self.qc.push_job(job)

        result = self.qc.wait_for_result(job.id, timeout=timeout)
        if result is None:
            return RuntimeResult(stderr="timeout waiting for job result", exit_code=1)
        return result
EOF
```

### 5.5 Artifact Store (`internal/artifacts/store.go` → `sandbox_platform/artifacts/store.py`)

```bash
cat > sandbox_platform/artifacts/store.py << 'EOF'
import io
import os
import pathlib
import tempfile

import structlog
from minio import Minio
from minio.error import S3Error

log = structlog.get_logger()


def _config_from_env() -> dict:
    return {
        "endpoint":   os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        "access_key": os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        "secret_key": os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        "bucket":     os.environ.get("MINIO_ARTIFACTS_BUCKET", "platform-artifacts"),
        "local_dir":  os.environ.get("ARTIFACTS_LOCAL_DIR", ""),
        "secure":     os.environ.get("MINIO_SECURE", "false").lower() == "true",
    }


class ArtifactStore:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or _config_from_env()
        endpoint = self.cfg["endpoint"].replace("http://", "").replace("https://", "")
        if not self.cfg["local_dir"]:
            self._client = Minio(
                endpoint,
                access_key=self.cfg["access_key"],
                secret_key=self.cfg["secret_key"],
                secure=self.cfg["secure"],
            )

    def ensure_bucket(self) -> None:
        if self.cfg["local_dir"]:
            pathlib.Path(self.cfg["local_dir"]).mkdir(parents=True, exist_ok=True)
            return
        bucket = self.cfg["bucket"]
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
            log.info("bucket created", bucket=bucket)

    def upload(self, artifact_id: str, name: str, data: bytes | io.IOBase) -> str:
        key = f"{artifact_id}/{name}"
        if self.cfg["local_dir"]:
            path = pathlib.Path(self.cfg["local_dir"]) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = data if isinstance(data, bytes) else data.read()
            path.write_bytes(raw)
            log.info("artifact saved locally", key=key)
            return key

        if isinstance(data, bytes):
            stream = io.BytesIO(data)
            size = len(data)
        else:
            raw = data.read()
            stream = io.BytesIO(raw)
            size = len(raw)

        self._client.put_object(self.cfg["bucket"], key, stream, size)
        log.info("artifact uploaded to minio", key=key)
        return key

    def download(self, key: str) -> bytes:
        if self.cfg["local_dir"]:
            return (pathlib.Path(self.cfg["local_dir"]) / key).read_bytes()
        response = self._client.get_object(self.cfg["bucket"], key)
        try:
            return response.read()
        finally:
            response.close()

    def url(self, key: str) -> str:
        if self.cfg["local_dir"]:
            return f"/artifacts/{key}"
        endpoint = self.cfg["endpoint"]
        bucket = self.cfg["bucket"]
        return f"{endpoint}/{bucket}/{key}"
EOF
```

### 5.6 Runtime: Firecracker (`sandbox_platform/runtime/firecracker/runtime.py`)

```bash
cat > sandbox_platform/runtime/firecracker/runtime.py << 'EOF'
import json
import os
import time
import threading
import uuid

import structlog

from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


def _detect_mode() -> str:
    forced = os.environ.get("FC_MODE", "")
    if forced in ("real", "sim"):
        log.info("FC mode from FC_MODE env", mode=forced)
        return forced
    if os.path.exists("/dev/kvm"):
        log.info("FC mode auto-detected: /dev/kvm present", mode="real")
        return "real"
    log.info("FC mode auto-detected: /dev/kvm absent", mode="sim")
    return "sim"


class FirecrackerRuntime:
    """
    Implements RuntimeEngine interface untuk Firecracker microVMs.

    Mode:
      real — jalankan VM dari MinIO snapshot via KVM (Linux only)
      sim  — simulasi, kembalikan mock output yang realistis
    """

    def __init__(self):
        self.mode = _detect_mode()
        self.snapshot_name = os.environ.get("SNAPSHOT_NAME", "python-v1")
        log.info("firecracker runtime initialised", mode=self.mode)

    @property
    def name(self) -> str:
        return f"firecracker-{self.mode}"

    @property
    def tier(self) -> Tier:
        return Tier.MICROVM

    def health(self) -> None:
        if self.mode == "sim":
            return
        fc_bin = os.environ.get("FC_BIN", "/usr/bin/firecracker")
        if not os.path.exists(fc_bin):
            raise RuntimeError(f"firecracker binary not found: {fc_bin}")

    def execute(self, job: Job) -> RuntimeResult:
        if self.mode == "real":
            return self._real_exec(job)
        return self._sim_exec(job)

    # ── Real execution ────────────────────────────────────────────────────────

    def _real_exec(self, job: Job) -> RuntimeResult:
        # Import pool hanya jika diperlukan (avoids Linux-only imports on macOS)
        from sandbox_platform.runtime.firecracker.pool import VMPool
        try:
            pool = VMPool.instance()
            vm = pool.acquire(timeout=30)
            try:
                return vm.execute(job.tool, job.input)
            finally:
                pool.release(vm)
        except Exception as exc:
            log.error("pool acquire failed, falling back to sim", error=str(exc))
            return self._sim_exec(job)

    # ── Simulation ────────────────────────────────────────────────────────────

    def _sim_exec(self, job: Job) -> RuntimeResult:
        start = time.time()
        log.info("fc execute", job_id=job.id, tool=job.tool, mode="sim")
        time.sleep(0.05)

        tool_output = self._sim_tool_output(job.tool, job.input)
        result = {
            "tool":      job.tool,
            "status":    "completed",
            "runtime":   "firecracker-sim",
            "vm_id":     f"fc-sim-{str(uuid.uuid4())[:8]}",
            "boot_ms":   20,
            "exec_ms":   int((time.time() - start) * 1000) - 20,
            "output":    tool_output,
            "snapshot":  self.snapshot_name,
            "sim_note":  "no /dev/kvm — using simulation (set FC_MODE=real on Linux with KVM)",
        }
        return RuntimeResult(stdout=json.dumps(result, indent=2), exit_code=0)

    def _sim_tool_output(self, tool: str, input_data: dict) -> dict | str:
        if tool == "python_run":
            code = input_data.get("code", "print('hello from Python')")
            return {"stdout": f"[sim] {code}\n=> hello from Python", "exit_code": 0}
        if tool == "bash_run":
            cmd = input_data.get("command", "")
            return {"stdout": f"[sim] $ {cmd}\n=> command executed", "exit_code": 0}
        return f"[sim] {tool} executed with input: {input_data}"
EOF
```

### 5.7 Runtime: WASM (`sandbox_platform/runtime/wasm/runtime.py`)

```bash
cat > sandbox_platform/runtime/wasm/runtime.py << 'EOF'
import json
import os
import shutil
import subprocess
import time

import structlog

from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


def _detect_mode(wasmtime_bin: str) -> str:
    forced = os.environ.get("WASM_MODE", "")
    if forced in ("real", "sim"):
        return forced
    if shutil.which(wasmtime_bin):
        return "real"
    return "sim"


HandlerFunc = callable  # Callable[[dict], str]


class WasmRuntime:
    def __init__(self):
        self._wasmtime = os.environ.get("WASMTIME_BIN", "wasmtime")
        self.mode = _detect_mode(self._wasmtime)
        self._handlers: dict[str, HandlerFunc] = {}
        self._register_builtins()
        log.info("wasm runtime initialised", mode=self.mode)

    @property
    def name(self) -> str:
        return f"wasm-{self.mode}"

    @property
    def tier(self) -> Tier:
        return Tier.WASM

    def health(self) -> None:
        if self.mode == "sim":
            return
        if not shutil.which(self._wasmtime):
            raise RuntimeError(f"wasmtime not found in PATH")

    def register_handler(self, tool: str, fn: HandlerFunc) -> None:
        self._handlers[tool] = fn

    def execute(self, job: Job) -> RuntimeResult:
        if self.mode == "real":
            return self._real_exec(job)
        return self._sim_exec(job)

    # ── Real execution ────────────────────────────────────────────────────────

    def _real_exec(self, job: Job) -> RuntimeResult:
        from sandbox_platform.runtime.wasm.module_store import ModuleStore
        store = ModuleStore.instance()
        module_path = store.ensure(job.tool)

        input_json = json.dumps(job.input).encode()
        timeout = int(os.environ.get("WASM_EXEC_TIMEOUT", "30"))

        try:
            result = subprocess.run(
                [self._wasmtime, "run", module_path],
                input=input_json,
                capture_output=True,
                timeout=timeout,
            )
            return RuntimeResult(
                stdout=result.stdout.decode(),
                stderr=result.stderr.decode(),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return RuntimeResult(stderr="execution timeout", exit_code=1)

    # ── Simulation ────────────────────────────────────────────────────────────

    def _sim_exec(self, job: Job) -> RuntimeResult:
        handler = self._handlers.get(job.tool) or self._handlers["echo"]
        try:
            output = handler(job.input)
            return RuntimeResult(stdout=output, exit_code=0)
        except Exception as exc:
            return RuntimeResult(stderr=str(exc), exit_code=1)

    def _register_builtins(self) -> None:
        def echo(inp):
            return json.dumps(inp, indent=2)

        def hello(inp):
            name = inp.get("name", "World")
            return f"Hello, {name}! (from WASM runtime)"

        def json_parse(inp):
            data = inp.get("data", "")
            parsed = json.loads(data)
            return json.dumps(parsed, indent=2)

        def html_parse(inp):
            html = inp.get("html", "")
            return f"Parsed HTML document ({len(html)} bytes)"

        def markdown_convert(inp):
            md = inp.get("markdown", "")
            return f"<html><body>{md}</body></html>"

        self._handlers = {
            "echo": echo, "hello": hello,
            "json_parse": json_parse, "html_parse": html_parse,
            "markdown_convert": markdown_convert,
        }
EOF
```

### 5.8 Runtime: GUI (`sandbox_platform/runtime/gui/runtime.py`)

```bash
cat > sandbox_platform/runtime/gui/runtime.py << 'EOF'
import json
import time

import structlog

from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


class GUIRuntime:
    @property
    def name(self) -> str:
        return "gui-runtime-stub"

    @property
    def tier(self) -> Tier:
        return Tier.GUI

    def health(self) -> None:
        pass  # Stub selalu healthy

    def execute(self, job: Job) -> RuntimeResult:
        log.info("gui stub executing", tool=job.tool, job_id=job.id)
        time.sleep(0.1)

        result = {
            "tool":       job.tool,
            "status":     "completed",
            "runtime":    "gui-stub",
            "session_id": f"browser-{job.id[:8]}",
            "input":      job.input,
            "output":     f"[stub] Executed {job.tool} in simulated browser session",
            "metadata": {
                "browser":    "chromium-121",
                "display":    ":99",
                "resolution": "1920x1080",
                "stream_url": f"ws://localhost:6080/vnc/{job.id[:8]}",
            },
        }
        return RuntimeResult(stdout=json.dumps(result, indent=2), exit_code=0)
EOF
```

### 5.9 Platform API (`cmd/platform-api/main.go` → `cmd/platform_api.py`)

```bash
cat > cmd/platform_api.py << 'EOF'
import io
import os
import time
import uuid
from contextlib import asynccontextmanager

import redis as redis_lib
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from sandbox_platform.artifacts.store import ArtifactStore
from sandbox_platform.queue.client import QueueClient
from sandbox_platform.router.router import Router
from sandbox_platform.session.manager import SessionManager
from sandbox_platform.types import JobStatus, Tier

log = structlog.get_logger()


# ── Pydantic request/response models ─────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    runtime: str = "wasm"

class ExecuteRequest(BaseModel):
    session_id: str = ""
    tool: str
    input: dict = {}


# ── App lifespan ──────────────────────────────────────────────────────────────

def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = _env("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/platform")
    redis_url = _env("REDIS_URL", "redis://localhost:6379/0")

    rdb = redis_lib.from_url(redis_url, decode_responses=True)
    session_mgr = SessionManager(dsn)
    session_mgr.init_db()

    qc = QueueClient(rdb)
    router = Router(qc)
    art_store = ArtifactStore()
    art_store.ensure_bucket()

    app.state.sessions = session_mgr
    app.state.router   = router
    app.state.artifacts = art_store
    app.state.rdb      = rdb

    log.info("platform-api started", port=8080)
    yield
    rdb.close()


app = FastAPI(title="sandbox-platform", version="0.1.0", lifespan=lifespan)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health(request: Request):
    rdb: redis_lib.Redis = request.app.state.rdb
    status = {}
    try:
        rdb.ping()
        status["redis"] = "healthy"
    except Exception as e:
        status["redis"] = f"unhealthy: {e}"

    overall = "healthy" if all(v == "healthy" for v in status.values()) else "degraded"
    code = 200 if overall == "healthy" else 503
    return JSONResponse({"status": overall, "version": "0.1.0", "services": status}, status_code=code)


@app.post("/sessions")
def create_session(body: CreateSessionRequest, request: Request):
    tier = Tier(body.runtime) if body.runtime else Tier.WASM
    sess = request.app.state.sessions.create(tier)
    return {"session_id": sess.id, "runtime": sess.runtime.value, "status": sess.status}


@app.post("/execute")
def execute(body: ExecuteRequest, request: Request):
    sessions: SessionManager = request.app.state.sessions
    router: Router = request.app.state.router

    if not body.tool:
        raise HTTPException(400, "tool is required")

    session_id = body.session_id
    if not session_id:
        tier = router.resolve(body.tool)
        sess = sessions.create(tier)
        session_id = sess.id
    else:
        sessions.get(session_id)  # validate exists

    tier = router.resolve(body.tool)
    job = sessions.create_job(session_id, body.tool, tier, body.input)
    job.input = body.input

    start = time.time()
    result = router.execute(job)
    duration_ms = int((time.time() - start) * 1000)

    if result.exit_code != 0:
        status = JobStatus.FAILED
    else:
        status = JobStatus.COMPLETED

    sessions.update_job(job.id, status, result.stdout, result.stderr, duration_ms)

    return {
        "job_id":        job.id,
        "status":        status.value,
        "output":        result.stdout,
        "error_message": result.stderr,
        "duration_ms":   duration_ms,
    }


@app.post("/artifacts")
async def upload_artifact(request: Request, file: UploadFile, session_id: str = "", name: str = ""):
    art_store: ArtifactStore = request.app.state.artifacts
    artifact_id = str(uuid.uuid4())
    filename = name or file.filename or "artifact"

    data = await file.read()
    key = art_store.upload(artifact_id, filename, data)

    return {
        "artifact_id": artifact_id,
        "key":  key,
        "url":  art_store.url(key),
        "size": len(data),
    }


@app.get("/artifacts/{artifact_id}/{filename}")
def download_artifact(artifact_id: str, filename: str, request: Request):
    art_store: ArtifactStore = request.app.state.artifacts
    key = f"{artifact_id}/{filename}"
    data = art_store.download(key)
    return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream")


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    uvicorn.run("cmd.platform_api:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    main()
EOF
```

### 5.10 FC Agent (`cmd/fc-agent/main.go` → `cmd/fc_agent.py`)

```bash
cat > cmd/fc_agent.py << 'EOF'
import os
import signal
import time

import redis as redis_lib
import structlog

from sandbox_platform.queue.client import QueueClient
from sandbox_platform.runtime.firecracker.runtime import FirecrackerRuntime
from sandbox_platform.types import Tier

log = structlog.get_logger(agent="fc")


def main():
    rdb = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    qc  = QueueClient(rdb)
    engine = FirecrackerRuntime()

    log.info("fc-agent started", tier=engine.tier.value, mode=engine.mode)

    running = True

    def _stop(sig, frame):
        nonlocal running
        log.info("fc-agent shutting down")
        running = False

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        job = qc.pop_job(Tier.MICROVM, timeout=2)
        if not job:
            continue

        log.info("received job", job_id=job.id, tool=job.tool)
        result = engine.execute(job)
        qc.publish_result(job.id, result)
        log.info("job done", job_id=job.id, exit_code=result.exit_code)


if __name__ == "__main__":
    main()
EOF
```

### 5.11 WASM Agent (`cmd/wasm-agent/main.go` → `cmd/wasm_agent.py`)

```bash
cat > cmd/wasm_agent.py << 'EOF'
import os
import signal

import redis as redis_lib
import structlog

from sandbox_platform.queue.client import QueueClient
from sandbox_platform.runtime.wasm.runtime import WasmRuntime
from sandbox_platform.types import Tier

log = structlog.get_logger(agent="wasm")


def main():
    rdb = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    qc  = QueueClient(rdb)
    engine = WasmRuntime()

    log.info("wasm-agent started", tier=engine.tier.value, mode=engine.mode)

    running = True

    def _stop(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        job = qc.pop_job(Tier.WASM, timeout=2)
        if not job:
            continue

        log.info("received job", job_id=job.id, tool=job.tool)
        result = engine.execute(job)
        qc.publish_result(job.id, result)

if __name__ == "__main__":
    main()
EOF
```

---

## Langkah 6 — Buat Makefile Python

```bash
cat > Makefile.python << 'EOF'
.PHONY: install dev test lint clean

install:
	uv pip install -e ".[dev]"

dev:
	REDIS_URL=redis://localhost:6379/0 \
	DATABASE_URL=postgresql://postgres:postgres@localhost:5432/platform \
	uvicorn cmd.platform_api:app --host 0.0.0.0 --port 8080 --reload

fc-agent:
	REDIS_URL=redis://localhost:6379/0 python -m cmd.fc_agent

wasm-agent:
	REDIS_URL=redis://localhost:6379/0 python -m cmd.wasm_agent

test:
	pytest tests/ -v --cov=sandbox_platform --cov-report=term-missing

lint:
	ruff check sandbox_platform/ cmd/
	mypy sandbox_platform/ --ignore-missing-imports

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .coverage htmlcov/ dist/ *.egg-info
EOF
```

---

## Langkah 7 — Hapus File Go (setelah Python verified)

> **Jalankan ini HANYA setelah semua test Python sudah hijau.**

```bash
# Verifikasi Python dulu
pytest tests/ -v

# Jika semua test hijau, hapus file Go
rm -f go.mod go.sum
rm -rf pkg/ internal/ runtime/*.go cmd/*/main.go
find cmd/ -name "*.go" -delete

# Hapus binary Go yang sudah di-build
rm -f bin/platform-api bin/fc-agent bin/wasm-agent bin/gui-agent
rm -f api-server wasm-agent  # binary di root

echo "Migrasi selesai"
```

---

## Langkah 8 — Verifikasi

```bash
# 1. Jalankan semua service lokal (butuh PostgreSQL + Redis)
make -f Makefile.python dev &
make -f Makefile.python fc-agent &
make -f Makefile.python wasm-agent &

# 2. Test health endpoint
curl http://localhost:8080/health

# 3. Test execute
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{"tool":"hello","input":{"name":"Anas"}}' | python -m json.tool

# 4. Test create session
curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime":"wasm"}' | python -m json.tool

# 5. Test python_run (Firecracker sim)
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{"tool":"python_run","input":{"code":"print(1+1)"}}' | python -m json.tool
```

---

## Referensi Cepat: Go vs Python

| Konsep | Go | Python |
|--------|----|--------|
| Goroutine | `go func()` | `threading.Thread` / `asyncio.create_task` |
| Channel | `chan T` | `queue.Queue` |
| Interface | `interface{}` | `Protocol` / ABC |
| Struct | `type Foo struct{}` | `@dataclass class Foo` |
| Error handling | `if err != nil` | `try/except` |
| JSON encode | `json.Marshal(v)` | `json.dumps(v)` |
| JSON decode | `json.Unmarshal(b, &v)` | `json.loads(b)` |
| Env var | `os.Getenv("KEY")` | `os.environ.get("KEY")` |
| HTTP server | `http.ListenAndServe` | `uvicorn.run(app)` |
| Build | `go build ./...` | `uv pip install -e .` |
| Run binary | `./platform-api` | `platform-api` (setelah install) |
| Test | `go test ./...` | `pytest` |
| Log JSON | `slog.Info(...)` | `structlog.get_logger().info(...)` |
