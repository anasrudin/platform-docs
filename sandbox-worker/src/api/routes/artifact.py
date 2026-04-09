"""Artifact routes."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse

log = structlog.get_logger()



def register(app_state: dict) -> APIRouter:
    router = APIRouter()  # new instance per call — safe for tests
    @router.post("/artifacts")
    async def upload_artifact(
        file: UploadFile = File(...),
        session_id: str = Form(""),
        name: str = Form(""),
    ) -> JSONResponse:
        content = await file.read()
        result = app_state["artifact_svc"].upload(content, name or file.filename or "artifact", session_id)
        return JSONResponse(content=result)

    @router.get("/artifacts/{artifact_id}/{name}")
    def download_artifact(artifact_id: str, name: str) -> Response:
        try:
            data = app_state["artifact_svc"].download(artifact_id, name)
        except Exception as exc:
            log.error("artifact download failed", err=str(exc))
            raise HTTPException(status_code=404, detail="Artifact not found")
        return Response(content=data, media_type="application/octet-stream")

    return router
