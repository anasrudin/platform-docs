"""Tracing middleware — creates a root span per HTTP request.

Injects trace_id into the structlog context so every log line
within a request carries the trace ID automatically.

Usage (in api/app.py):
    app.add_middleware(TracingMiddleware)
"""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from adapters.tracing import get_tracer

log = structlog.get_logger()


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        tracer = get_tracer()
        trace_id = str(uuid.uuid4()).replace("-", "")[:16]
        start = time.monotonic()

        attrs = {
            "http.method": request.method,
            "http.path": request.url.path,
            "http.client": (request.client.host if request.client else "unknown"),
        }

        with tracer.start_span("http.request", attrs) as span:
            # Bind trace_id to structlog for the duration of this request
            structlog.contextvars.bind_contextvars(trace_id=trace_id)
            try:
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                return response
            except Exception as exc:
                span.record_exception(exc)
                raise
            finally:
                duration_ms = int((time.monotonic() - start) * 1000)
                span.set_attribute("http.duration_ms", duration_ms)
                structlog.contextvars.clear_contextvars()
