"""fc-agent — Firecracker snapshot agent entry point.

Downloads the named snapshot from MinIO on startup, then serves a health
endpoint so Consul can monitor the agent. Delegates execution to the
Firecracker runtime (sim or real based on FC_MODE / /dev/kvm).

Entry point: `fc-agent` (registered in pyproject.toml [project.scripts])
"""
from __future__ import annotations

import signal
import sys
import threading

import structlog
import uvicorn

from adapters.registry.health_server import make_health_app
from config.settings import settings
from runtime.firecracker import Config, Runtime, SnapshotStore, detect_mode

log = structlog.get_logger()

_SHUTDOWN = threading.Event()


def _handle_signal(sig, frame) -> None:
    log.info("fc-agent shutting down", signal=sig)
    _SHUTDOWN.set()


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    cfg = Config()
    mode = detect_mode()
    log.info("fc-agent starting", mode=mode, snapshot=cfg.snapshot_name)

    # Ensure snapshot is cached locally (logs "snapshot not cached, downloading
    # from MinIO  name=<snapshot>" on first run, "snapshot cache hit" on subsequent)
    store = SnapshotStore(
        endpoint=cfg.minio_endpoint,
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key,
        bucket=cfg.minio_bucket,
        cache_dir=cfg.snapshot_cache_dir,
    )
    snap = store.ensure(cfg.snapshot_name)
    log.info("snapshot ready", mode=mode, snapshot=cfg.snapshot_name,
             state_file=snap.state_file)

    # Build the runtime (sim or real)
    runtime = Runtime()

    # Start health endpoint in a daemon thread
    health_app = make_health_app(
        runtime_name=f"fc-agent-{mode}",
        pool_size_fn=runtime.pool_size,
    )
    health_port = settings.api.health_port
    health_cfg = uvicorn.Config(health_app, host="0.0.0.0", port=health_port,
                                log_level="warning")
    health_server = uvicorn.Server(health_cfg)
    health_thread = threading.Thread(target=health_server.run, daemon=True,
                                     name="fc-health")
    health_thread.start()
    log.info("fc-agent health server started", port=health_port)

    # Block until shutdown signal
    _SHUTDOWN.wait()
    log.info("fc-agent stopped")
