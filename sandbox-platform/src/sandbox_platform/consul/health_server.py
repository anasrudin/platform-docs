"""Lightweight per-agent health HTTP server.

Each runtime agent (fc, wasm, gui) starts one of these in a daemon thread so
that Consul can poll GET /health without touching the queue-polling loop.

Usage::

    from sandbox_platform.consul.health_server import make_health_app, start_health_server

    # For tests — use the app directly with FastAPI TestClient:
    app = make_health_app("firecracker-sim", pool_size_fn=lambda: runtime.pool_size())

    # For production — run in a background daemon thread:
    start_health_server(port=8081, runtime_name="firecracker-sim",
                        pool_size_fn=lambda: runtime.pool_size())
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI, Request, Response
from sandbox_platform.middleware.trace import TraceIDMiddleware


def make_health_app(
    runtime_name: str,
    pool_size_fn: Callable[[], int],
) -> FastAPI:
    """Build a FastAPI app with a single GET /health endpoint."""
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)

    @app.get("/health")
    def health(request: Request, response: Response) -> dict:
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

    thread = threading.Thread(
        target=server.run, daemon=True, name=f"health-{runtime_name}"
    )
    thread.start()
