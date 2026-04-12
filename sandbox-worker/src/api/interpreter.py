"""interpreter.py — Minimal Firecracker code interpreter API.

Single endpoint: POST /run
Accepts Python or bash code, executes in a real Firecracker microVM,
returns stdout/stderr/exit_code.  No sessions, no workflows, no auth.

Usage:
    FC_MODE=real platform-interpreter
    FC_MODE=sim  platform-interpreter   # for local dev without KVM
"""
from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from adapters.storage.snapshot_blob import SnapshotBlobStore
from orchestrator.lifecycle import VMLifecycleManager

log = structlog.get_logger()

# ── Config ─────────────────────────────────────────────────────────────────────

API_PORT        = int(os.environ.get("API_PORT", "8090"))
FC_MODE         = os.environ.get("FC_MODE", "auto")
FC_POOL_SIZE    = int(os.environ.get("FC_POOL_SIZE", "1"))
FC_BINARY       = os.environ.get("FC_BINARY_PATH", "/usr/bin/firecracker")
SNAPSHOT_NAME   = os.environ.get("SNAPSHOT_NAME", "python-v1")
MINIO_ENDPOINT  = os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:9000")
MINIO_KEY       = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET    = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET    = os.environ.get("FC_SNAPSHOT_BUCKET", "platform-snapshots")

# ── Lifespan ───────────────────────────────────────────────────────────────────

_lifecycle: VMLifecycleManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _lifecycle

    storage = SnapshotBlobStore(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_KEY,
        secret_key=MINIO_SECRET,
        bucket=MINIO_BUCKET,
    )

    _lifecycle = VMLifecycleManager(
        storage=storage,
        snapshot_name=SNAPSHOT_NAME,
        pool_size=FC_POOL_SIZE,
        firecracker_bin=FC_BINARY,
        dev_mode=False,
    )
    _lifecycle.start()
    log.info("interpreter started", port=API_PORT, fc_mode=FC_MODE, pool_size=FC_POOL_SIZE)

    yield

    if _lifecycle:
        _lifecycle.stop()
    log.info("interpreter stopped")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Firecracker Code Interpreter", version="1.0.0", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    language: Literal["python", "bash"] = "python"
    code: str
    timeout: int = 30  # seconds


class RunResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    runtime: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    if _lifecycle is None:
        return {"status": "starting"}

    sim = getattr(_lifecycle, "_sim_mode", False)
    pool = getattr(_lifecycle, "_pool", None)
    warmup = getattr(_lifecycle, "_warmup_thread", None)

    if sim:
        return {"status": "healthy", "mode": "sim", "pool_available": 1}

    if pool is None:
        return {"status": "starting", "mode": "real", "pool_available": 0}

    available = pool._ready.qsize()
    if warmup and warmup.is_alive():
        status = "warming_up"
    elif available > 0:
        status = "healthy"
    else:
        status = "degraded"

    return {"status": status, "mode": "real", "pool_available": available}


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest):
    if _lifecycle is None:
        raise HTTPException(503, "Service starting")

    tool = "python_run" if req.language == "python" else "bash_run"
    input_data: dict = {"code": req.code} if req.language == "python" else {"command": req.code}

    t0 = time.monotonic()
    try:
        vm = _lifecycle.acquire(timeout=req.timeout)
    except TimeoutError:
        raise HTTPException(503, "No VM available — pool warming up or exhausted")

    try:
        result = vm.execute(tool, input_data)
    finally:
        _lifecycle.release(vm)

    duration_ms = int((time.monotonic() - t0) * 1000)

    # Parse guest response output (JSON string from guest agent)
    try:
        out = json.loads(result.stdout)
        stdout = out.get("stdout", result.stdout)
        stderr = out.get("stderr", result.stderr)
        exit_code = int(out.get("exit_code", result.exit_code))
    except (json.JSONDecodeError, AttributeError):
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.exit_code

    sim_mode = getattr(_lifecycle, "_sim_mode", False)
    return RunResponse(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms,
        runtime="firecracker-sim" if sim_mode else "firecracker",
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    uvicorn.run("api.interpreter:app", host="0.0.0.0", port=API_PORT, log_level="warning")


if __name__ == "__main__":
    main()
