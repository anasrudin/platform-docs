"""Sandbox-platform worker API — FastAPI app wired to local VM pool.

Each Nomad client node runs one instance of this app.
HAProxy routes requests across nodes; Consul registers this node.

Structure:
  api/app.py          ← lifespan + app factory
  api/routes/         ← one file per resource
  api/middleware/     ← auth, tracing
  api/schemas/        ← Pydantic request/response models
"""
from __future__ import annotations

import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI

from adapters.tracing import init_tracer
from adapters.registry.consul import ConsulClient
from adapters.registry.health_server import start_health_server
from adapters.storage.s3_compat import Config as ArtifactConfig, Store as ArtifactStore, mc_available
from adapters.storage.local import PackageStore, LocalStorage
from api.middleware.auth import TenantAuthMiddleware, auth_config_from_env
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.tracing import TracingMiddleware
from api.routes import artifact, execute, health, hibernation, package, session, streaming, workflow, workspace
from config.settings import settings
from orchestrator.hibernation import HibernationOrchestrator
from orchestrator.lifecycle import VMLifecycleManager
from orchestrator.workspace import WorkspaceMounter
from service.artifact import ArtifactService
from service.execution import ExecutionService
from service.health import HealthService
from service.hibernation import HibernationService
from service.package import PackageService
from service.session import SessionService
from service.streaming import StreamingService
from service.workspace import WorkspaceService

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


log = structlog.get_logger()

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings
    _configure_logging(cfg.api.dev_mode)

    # Tracing
    init_tracer(
        driver=cfg.tracing.enabled and "otel" or "noop",
        service_name=cfg.tracing.service_name,
        otlp_endpoint=cfg.tracing.otlp_endpoint,
    )

    # VM lifecycle — local Firecracker pool on this node
    lifecycle_mgr = VMLifecycleManager(
        storage=None,  # snapshot storage wired below
        snapshot_name=cfg.firecracker.snapshot_bucket,
        pool_size=cfg.firecracker.pool_size,
        firecracker_bin=cfg.firecracker.binary_path,
        dev_mode=cfg.firecracker.dev_mode,
    )
    lifecycle_mgr.start()
    _state["lifecycle_mgr"] = lifecycle_mgr

    # Artifact store
    art_cfg = ArtifactConfig.from_env()
    if (
        not art_cfg.local_dir
        and not mc_available()
        and ("localhost" in art_cfg.endpoint or "127.0.0.1" in art_cfg.endpoint)
    ):
        art_cfg.local_dir = str(Path(tempfile.gettempdir()) / "platform-artifacts")
        log.info("artifact store falling back to local filesystem", dir=art_cfg.local_dir)
    art_store = ArtifactStore(art_cfg)
    try:
        art_store.ensure_bucket()
    except Exception as exc:
        log.warning("artifact bucket init skipped", err=str(exc))

    # Package store
    pkg_local_dir = cfg.packages.local_dir or str(Path(tempfile.gettempdir()) / "platform-packages")

    # Services
    _state["health_svc"] = HealthService(lifecycle_mgr)
    _state["session_svc"] = SessionService()
    _state["exec_svc"] = ExecutionService(lifecycle_mgr)
    _state["artifact_svc"] = ArtifactService(art_store)
    _state["package_svc"] = PackageService(PackageStore(local_dir=pkg_local_dir))

    # Hibernation — optional
    if cfg.hibernation.enabled:
        hibernate_storage = LocalStorage(
            cfg.storage.local_dir or str(Path(tempfile.gettempdir()) / "platform-hibernate")
        )
        hibernate_orch = HibernationOrchestrator(hibernate_storage)
        _state["hibernation_svc"] = HibernationService(
            orchestrator=hibernate_orch,
            idle_timeout=cfg.hibernation.idle_timeout,
            ttl=cfg.hibernation.ttl,
        )
        log.info("hibernation enabled", idle_timeout=cfg.hibernation.idle_timeout)
    else:
        _state["hibernation_svc"] = None

    # Workspace
    ws_local_dir = cfg.workspace.local_dir or str(Path(tempfile.gettempdir()) / "platform-workspaces")
    _ws_storage = LocalStorage(ws_local_dir)
    _ws_mounter = WorkspaceMounter(_ws_storage, bucket_prefix="workspaces")
    _state["workspace_svc"] = WorkspaceService(
        storage=_ws_storage,
        mounter=_ws_mounter,
        driver=cfg.workspace.driver,
        max_size_mb=cfg.workspace.max_size_mb,
    )

    # Streaming
    _state["streaming_svc"] = StreamingService(
        max_timeout=cfg.streaming.max_timeout,
        buffer_size=cfg.streaming.buffer_size,
    )

    # Workflow
    from service.workflow import WorkflowService
    def _workflow_executor(tool: str, input_data: dict) -> dict:
        return _state["exec_svc"].execute({"tool": tool, "input": input_data})
    _state["workflow_svc"] = WorkflowService(
        executor=_workflow_executor,
        max_steps=cfg.workflow.max_steps,
    )

    # Consul registration — optional
    if cfg.consul.enabled:
        consul = ConsulClient()
        start_health_server(port=cfg.api.health_port)
        consul.register(
            name="sandbox-worker",
            port=cfg.api.port,
            tags=["sandbox", "worker"],
        )
        log.info("registered with consul", port=cfg.api.port)

    log.info("sandbox-worker started", port=cfg.api.port, pool_size=cfg.firecracker.pool_size)
    yield

    lifecycle_mgr.stop()
    log.info("sandbox-worker stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="sandbox-platform-worker", lifespan=lifespan)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TracingMiddleware)
    _auth_cfg = auth_config_from_env()
    app.add_middleware(TenantAuthMiddleware, enabled=_auth_cfg["enabled"])

    app.include_router(health.register(_state))
    app.include_router(session.register(_state))
    app.include_router(execute.register(_state))
    app.include_router(artifact.register(_state))
    app.include_router(package.register(_state))
    app.include_router(hibernation.register(_state))
    app.include_router(streaming.register(_state))
    app.include_router(workspace.register(_state))
    app.include_router(workflow.register(_state))

    return app


app = create_app()


def main() -> None:
    uvicorn.run("api.app:app", host=settings.api.host, port=settings.api.port, log_level="info")


if __name__ == "__main__":
    main()
