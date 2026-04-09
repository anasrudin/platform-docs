"""Session routes."""
from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/sessions")
    async def create_session(body: dict = Body(default_factory=dict)) -> JSONResponse:
        runtime_str = body.get("runtime", "wasm")
        snapshot_mode_str = body.get("snapshot_mode", "clean")
        result = await app_state["session_svc"].create(runtime_str, snapshot_mode_str)
        return JSONResponse(content=result)

    return router
