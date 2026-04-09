"""Health route."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse




def register(app_state: dict) -> APIRouter:
    router = APIRouter()  # new instance per call — safe for tests
    @router.get("/health")
    def health() -> JSONResponse:
        result = app_state["health_svc"].check()
        return JSONResponse(content=result, status_code=200 if result["status"] == "healthy" else 503)

    return router
