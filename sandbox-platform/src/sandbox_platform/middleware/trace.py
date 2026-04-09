import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRACE_ID_HEADER = "X-Trace-ID"


class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get(TRACE_ID_HEADER)
        if not trace_id:
            trace_id = str(uuid.uuid4())

        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            response: Response = await call_next(request)
            response.headers[TRACE_ID_HEADER] = trace_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("trace_id")


def get_trace_id() -> str:
    return structlog.contextvars.get_contextvars().get("trace_id", "")
