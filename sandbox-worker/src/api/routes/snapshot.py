"""Snapshot routes — DELETE /snapshots/{session_id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.delete("/snapshots/{session_id}", status_code=204)
    def delete_snapshot(session_id: str) -> Response:
        downloader = app_state.get("snapshot_downloader")
        if downloader is None:
            raise HTTPException(status_code=503, detail="Snapshot service not configured")
        downloader.delete_session_snapshot(session_id)
        return Response(status_code=204)

    return router
