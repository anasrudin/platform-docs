"""Hibernation routes — POST /sessions/{id}/hibernate and /restore."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse


def register(app_state: dict) -> APIRouter:
    router = APIRouter()  # new instance per call — safe for tests

    @router.post("/sessions/{session_id}/hibernate")
    def hibernate_session(session_id: str) -> JSONResponse:
        svc = app_state.get("hibernation_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Hibernation not enabled (HIBERNATE_ENABLED=false)")
        try:
            result = svc.hibernate(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return JSONResponse(content=result, status_code=202)

    @router.post("/sessions/{session_id}/restore")
    def restore_session(session_id: str) -> JSONResponse:
        svc = app_state.get("hibernation_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Hibernation not enabled (HIBERNATE_ENABLED=false)")
        try:
            result = svc.restore(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return JSONResponse(content=result)

    return router
