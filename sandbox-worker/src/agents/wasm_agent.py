"""wasm-agent — WASM runtime agent entry point (stub)."""
from __future__ import annotations

import signal
import threading

import structlog
import uvicorn

from adapters.registry.health_server import make_health_app
from config.settings import settings
from runtime.wasm import Runtime

log = structlog.get_logger()

_SHUTDOWN = threading.Event()


def _handle_signal(sig, frame) -> None:
    log.info("wasm-agent shutting down", signal=sig)
    _SHUTDOWN.set()


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    runtime = Runtime()
    log.info("wasm-agent starting", mode=runtime.name())

    health_app = make_health_app(
        runtime_name=runtime.name(),
        pool_size_fn=lambda: 0,
    )
    health_port = settings.api.health_port + 1
    health_cfg = uvicorn.Config(health_app, host="0.0.0.0", port=health_port,
                                log_level="warning")
    health_server = uvicorn.Server(health_cfg)
    health_thread = threading.Thread(target=health_server.run, daemon=True,
                                     name="wasm-health")
    health_thread.start()
    log.info("wasm-agent health server started", port=health_port)

    _SHUTDOWN.wait()
    log.info("wasm-agent stopped")
