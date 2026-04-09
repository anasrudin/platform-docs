"""Execution route."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse




def register(app_state: dict) -> APIRouter:
    router = APIRouter()  # new instance per call — safe for tests
    @router.post("/execute")
    def execute(request: Request, body: dict) -> JSONResponse:
        try:
            result = app_state["exec_svc"].execute(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Session not found: {exc}")
        return JSONResponse(content=result)

    return router
