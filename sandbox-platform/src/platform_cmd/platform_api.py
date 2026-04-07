"""Platform API — FastAPI entry point.

Mirrors cmd/platform-api/main.go.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from sandbox_platform.artifacts.store import Config as ArtifactConfig
from sandbox_platform.artifacts.store import Store as ArtifactStore
from sandbox_platform.artifacts.store import mc_available
from sandbox_platform.queue.client import Client as QueueClient
from sandbox_platform.queue.client import new_redis_client
from sandbox_platform.router.router import Router
from sandbox_platform.session.manager import Manager as SessionManager
from sandbox_platform.session.manager import new_connection
from sandbox_platform.types import (
    ArtifactUploadResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    JobStatus,
    Tier,
)

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger()


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


# ── App state ──────────────────────────────────────────────────────────────────

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database
    dsn = _env_or("DATABASE_URL",
                   "postgres://postgres:postgres@localhost:5432/platform?sslmode=disable")
    conn = new_connection(dsn)
    session_mgr = SessionManager(conn)
    session_mgr.init_db()
    _state["session_mgr"] = session_mgr
    _state["db_conn"] = conn

    # Redis
    redis_url = _env_or("REDIS_URL", "redis://localhost:6379/0")
    rdb = new_redis_client(redis_url)
    rdb.ping()
    _state["rdb"] = rdb
    qc = QueueClient(rdb)
    _state["qc"] = qc

    # Artifact store
    art_cfg = ArtifactConfig.from_env()
    if (
        not art_cfg.local_dir
        and not mc_available()
        and ("localhost" in art_cfg.endpoint or "127.0.0.1" in art_cfg.endpoint)
    ):
        art_cfg.local_dir = str(Path(tempfile.gettempdir()) / "platform-artifacts")
        log.info("artifact store falling back to local filesystem",
                 dir=art_cfg.local_dir, endpoint=art_cfg.endpoint)
    art_store = ArtifactStore(art_cfg)
    try:
        art_store.ensure_bucket()
    except Exception as exc:
        log.warning("artifact bucket init skipped", err=str(exc))
    _state["art_store"] = art_store

    # Router
    router = Router(qc)
    _state["router"] = router

    log.info("platform-api started", addr=":8080")
    yield

    conn.close()
    rdb.close()


app = FastAPI(title="sandbox-platform", lifespan=lifespan)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> JSONResponse:
    conn = _state["db_conn"]
    rdb = _state["rdb"]
    services: dict[str, str] = {}

    try:
        conn.cursor().execute("SELECT 1")
        services["postgres"] = "healthy"
    except Exception as exc:
        services["postgres"] = f"unhealthy: {exc}"

    try:
        rdb.ping()
        services["redis"] = "healthy"
    except Exception as exc:
        services["redis"] = f"unhealthy: {exc}"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"
    resp = HealthResponse(status=overall, version="0.1.0-local", services=services)
    status_code = 200 if overall == "healthy" else 503
    return JSONResponse(
        content={"status": resp.status, "version": resp.version, "services": resp.services},
        status_code=status_code,
    )


# ── Sessions ───────────────────────────────────────────────────────────────────

@app.post("/sessions")
def create_session(body: dict = None) -> JSONResponse:
    session_mgr: SessionManager = _state["session_mgr"]
    runtime_str = (body or {}).get("runtime", "wasm")
    try:
        tier = Tier(runtime_str)
    except ValueError:
        tier = Tier.WASM

    sess = session_mgr.create(tier)
    resp = CreateSessionResponse(
        session_id=sess.id,
        runtime=sess.runtime,
        status=sess.status,
    )
    return JSONResponse(content={
        "session_id": resp.session_id,
        "runtime": resp.runtime.value,
        "status": resp.status,
    })


# ── Execute ────────────────────────────────────────────────────────────────────

@app.post("/execute")
def execute(request: Request, body: dict) -> JSONResponse:
    import time

    session_mgr: SessionManager = _state["session_mgr"]
    router: Router = _state["router"]

    tool = body.get("tool", "")
    if not tool:
        raise HTTPException(status_code=400, detail="Tool name is required")

    session_id = body.get("session_id", "")
    if session_id:
        try:
            sess = session_mgr.get(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    else:
        tier = router.resolve(tool)
        sess = session_mgr.create(tier)
        session_id = sess.id

    input_data = body.get("input") or {}
    input_bytes = json.dumps(input_data).encode()
    tier = router.resolve(tool)

    from sandbox_platform.types import Job, JobStatus
    from datetime import datetime

    job = session_mgr.create_job(session_id, tool, tier, input_bytes)
    job.input = input_data

    start = time.monotonic()
    result = router.execute(job)
    duration_ms = int((time.monotonic() - start) * 1000)

    if result.exit_code != 0:
        status = JobStatus.FAILED
        err_msg = result.stderr or f"Process exited with code {result.exit_code}"
    else:
        status = JobStatus.COMPLETED
        err_msg = result.stderr

    session_mgr.update_job(job.id, status, result.stdout, err_msg, duration_ms)

    return JSONResponse(content={
        "job_id": job.id,
        "status": status.value,
        "output": result.stdout,
        "error_message": err_msg,
        "duration_ms": duration_ms,
    })


# ── Artifacts ──────────────────────────────────────────────────────────────────

@app.post("/artifacts")
async def upload_artifact(
    file: UploadFile = File(...),
    session_id: str = Form(""),
    name: str = Form(""),
) -> JSONResponse:
    art_store: ArtifactStore = _state["art_store"]
    artifact_name = name or file.filename or "artifact"
    artifact_id = str(uuid.uuid4())

    content = await file.read()
    import io
    key = art_store.upload(artifact_id, artifact_name, io.BytesIO(content))

    log.info("artifact uploaded", artifact_id=artifact_id,
             session_id=session_id, name=artifact_name, size=len(content))

    return JSONResponse(content={
        "artifact_id": artifact_id,
        "key": key,
        "url": art_store.url(key),
        "size": len(content),
    })


@app.get("/artifacts/{artifact_id}/{name}")
def download_artifact(artifact_id: str, name: str) -> Response:
    art_store: ArtifactStore = _state["art_store"]
    key = f"{artifact_id}/{name}"
    import io
    buf = io.BytesIO()
    try:
        art_store.download(key, buf)
    except Exception as exc:
        log.error("artifact download failed", key=key, err=str(exc))
        raise HTTPException(status_code=404, detail="Artifact not found")
    buf.seek(0)
    return Response(content=buf.read(), media_type="application/octet-stream")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    uvicorn.run("platform_cmd.platform_api:app", host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
