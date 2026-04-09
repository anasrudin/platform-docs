"""Workflow routes — POST /workflows, GET /workflows/{id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from service.workflow import CyclicDependencyError, WorkflowValidationError


class WorkflowRequest(BaseModel):
    name: str
    steps: list[dict]


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/workflows", status_code=202)
    def create_workflow(body: WorkflowRequest) -> JSONResponse:
        svc = app_state.get("workflow_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workflow service not configured")
        try:
            result = svc.create(body.name, body.steps)
        except (WorkflowValidationError, CyclicDependencyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return JSONResponse(content=result, status_code=202)

    @router.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str) -> JSONResponse:
        svc = app_state.get("workflow_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workflow service not configured")
        try:
            result = svc.get(workflow_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return JSONResponse(content=result)

    return router
