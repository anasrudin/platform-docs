"""Session routes."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse




def register(app_state: dict) -> APIRouter:
    router = APIRouter()  # new instance per call — safe for tests
    @router.post("/sessions")
    async def create_session(body: dict = None) -> JSONResponse:
        runtime_str = (body or {}).get("runtime", "wasm")
        return JSONResponse(content=await app_state["session_svc"].create(runtime_str))

    return router
