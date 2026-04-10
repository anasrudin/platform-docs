"""gui-agent — GUI (Chromium) runtime agent entry point (stub)."""
from __future__ import annotations

import signal
import threading

import structlog
import uvicorn

from adapters.registry.health_server import make_health_app
from config.settings import settings
from runtime.gui import Runtime

log = structlog.get_logger()

_SHUTDOWN = threading.Event()


def _handle_signal(sig, frame) -> None:
    log.info("gui-agent shutting down", signal=sig)
    _SHUTDOWN.set()


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    runtime = Runtime()
    log.info("gui-agent starting", mode=runtime.name())

    health_app = make_health_app(
        runtime_name=runtime.name(),
        pool_size_fn=lambda: 0,
    )
    health_port = settings.api.health_port + 2
    health_cfg = uvicorn.Config(health_app, host="0.0.0.0", port=health_port,
                                log_level="warning")
    health_server = uvicorn.Server(health_cfg)
    health_thread = threading.Thread(target=health_server.run, daemon=True,
                                     name="gui-health")
    health_thread.start()
    log.info("gui-agent health server started", port=health_port)

    _SHUTDOWN.wait()
    log.info("gui-agent stopped")
