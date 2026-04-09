"""Lightweight per-agent health HTTP server.

Each runtime agent (fc, wasm, gui) starts one of these in a daemon thread so
that Consul can poll GET /health without touching the queue-polling loop.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI


def make_health_app(
    runtime_name: str,
    pool_size_fn: Callable[[], int],
) -> FastAPI:
    """Build a FastAPI app with a single GET /health endpoint."""
    app = FastAPI()

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "runtime": runtime_name,
            "pool_size": pool_size_fn(),
        }

    return app


def start_health_server(
    port: int,
    runtime_name: str,
    pool_size_fn: Callable[[], int],
) -> None:
    """Start uvicorn in a daemon thread. Returns immediately."""
    app = make_health_app(runtime_name, pool_size_fn)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name=f"health-{runtime_name}")
    thread.start()


__all__ = ["make_health_app", "start_health_server"]
