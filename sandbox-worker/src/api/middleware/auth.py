"""Tenant authentication middleware.

When TENANT_ISOLATION=false (default):
  - All requests proceed; request.state.tenant_id = "default"
  - Backward-compatible single-tenant mode.

When TENANT_ISOLATION=true:
  - Reads tenant_id from (in priority order):
    1. X-Tenant-ID header (dev/testing convenience)
    2. Authorization: Bearer <base64url-json> where JSON has {"tenant_id": "..."}
  - Missing / invalid credentials → 401 JSON response.
"""
from __future__ import annotations

import base64
import json
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TenantAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = False) -> None:
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled:
            request.state.tenant_id = "default"
            return await call_next(request)

        tenant_id = self._extract_tenant(request)
        if tenant_id is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid authentication credentials"},
            )
        request.state.tenant_id = tenant_id
        return await call_next(request)

    @staticmethod
    def _extract_tenant(request: Request) -> str | None:
        # 1. Direct header (dev/testing)
        direct = request.headers.get("X-Tenant-ID", "").strip()
        if direct:
            return direct

        # 2. Authorization: Bearer <token>
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            tid = _decode_tenant_from_token(token)
            if tid:
                return tid

        return None


def _decode_tenant_from_token(token: str) -> str | None:
    """Decode tenant_id from a base64url-encoded JSON token (simplified, no signature check)."""
    try:
        # Accept both plain base64 JSON and JWT (decode payload segment only)
        parts = token.split(".")
        payload_b64 = parts[1] if len(parts) == 3 else parts[0]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        return payload.get("tenant_id") or None
    except Exception:
        return None


def auth_config_from_env() -> dict:
    return {"enabled": os.environ.get("TENANT_ISOLATION", "").lower() == "true"}
