"""Streaming routes — WebSocket and SSE endpoints for live VM output."""
from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

log = structlog.get_logger()


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.websocket("/sessions/{session_id}/execute/stream")
    async def ws_stream(websocket: WebSocket, session_id: str):
        """WebSocket endpoint — client sends tool+input, server streams output."""
        svc = app_state.get("streaming_svc")
        if svc is None:
            await websocket.close(code=1011, reason="Streaming not configured")
            return

        await websocket.accept()
        try:
            raw = await websocket.receive_text()
            body = json.loads(raw)
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": f"invalid request: {exc}"})
            await websocket.close()
            return

        tool = body.get("tool", "")
        input_data = body.get("input", {})
        if not tool:
            await websocket.send_json({"type": "error", "message": "tool is required"})
            await websocket.close()
            return

        log.info("ws stream started", session_id=session_id, tool=tool)
        try:
            async for chunk in svc.stream(session_id, tool, input_data):
                await websocket.send_json(chunk)
                if chunk.get("type") in ("done", "error"):
                    break
        except WebSocketDisconnect:
            log.info("ws client disconnected", session_id=session_id)
        except Exception as exc:
            log.error("ws stream error", session_id=session_id, err=str(exc))
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    @router.get("/sessions/{session_id}/execute/stream")
    async def sse_stream(session_id: str, tool: str = "", input: str = "{}"):
        """SSE fallback — GET with tool and input query params."""
        svc = app_state.get("streaming_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Streaming not configured")
        if not tool:
            raise HTTPException(status_code=400, detail="tool query param required")

        try:
            input_data = json.loads(input)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="input must be valid JSON")

        async def event_generator():
            async for chunk in svc.stream(session_id, tool, input_data):
                yield f"data: {json.dumps(chunk)}\n\n"
                if chunk.get("type") in ("done", "error"):
                    break

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return router
