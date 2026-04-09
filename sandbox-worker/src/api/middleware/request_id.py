"""RequestIDMiddleware — propagate X-Request-ID ke semua log dalam satu request."""
from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate atau ambil X-Request-ID dari header, bind ke structlog context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Gunakan ID dari client kalau ada, generate baru kalau tidak ada
        request_id = request.headers.get("X-Request-ID") or str(uuid4())[:8]
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
