"""Workspace routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class CreateWorkspaceRequest(BaseModel):
    name: str
    tenant_id: str = "default"


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/workspaces")
    def create_workspace(body: CreateWorkspaceRequest) -> JSONResponse:
        svc = app_state.get("workspace_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workspace service not configured")
        result = svc.create(body.name, body.tenant_id)
        return JSONResponse(content=result, status_code=201)

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str) -> JSONResponse:
        svc = app_state.get("workspace_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workspace service not configured")
        try:
            return JSONResponse(content=svc.get(workspace_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.delete("/workspaces/{workspace_id}", status_code=204)
    def delete_workspace(workspace_id: str) -> None:
        svc = app_state.get("workspace_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workspace service not configured")
        try:
            svc.delete(workspace_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/workspaces/{workspace_id}/files")
    def list_files(workspace_id: str) -> JSONResponse:
        svc = app_state.get("workspace_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workspace service not configured")
        try:
            files = svc.list_files(workspace_id)
            return JSONResponse(content={"files": files, "count": len(files)})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return router
