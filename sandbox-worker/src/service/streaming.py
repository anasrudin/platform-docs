"""StreamingService — coordinates WebSocket clients and VM output streams.

Multiple clients can subscribe to the same session (broadcast).
Connection lifecycle:
  - client connects to WS endpoint
  - StreamingService opens a stream from the VM via communication/stream.py
  - chunks are broadcast to all subscribers
  - {"type": "done"} signals end; connection is closed after
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import structlog

from adapters.tracing import get_tracer
from communication.stream import stream_execute

log = structlog.get_logger()


class StreamingService:
    def __init__(self, max_timeout: int = 300, buffer_size: int = 4096) -> None:
        self._max_timeout = max_timeout
        self._buffer_size = buffer_size
        # session_id → list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def stream(
        self,
        session_id: str,
        tool: str,
        input_data: dict,
        cid: int = 0,
        tcp_addr: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield output chunks for a single subscriber, broadcasting to all."""
        tracer = get_tracer()
        queue: asyncio.Queue = asyncio.Queue()

        with tracer.start_span("service.streaming.stream", {"session_id": session_id, "tool": tool}):
            # Register subscriber
            self._subscribers.setdefault(session_id, []).append(queue)
            log.info("stream subscriber added", session_id=session_id, tool=tool,
                     subscribers=len(self._subscribers[session_id]))
            try:
                # Run the stream producer in a background task so multiple
                # subscribers can receive the same chunks concurrently
                producer_task = asyncio.create_task(
                    self._produce(session_id, tool, input_data, cid, tcp_addr)
                )

                while True:
                    chunk = await asyncio.wait_for(queue.get(), timeout=self._max_timeout + 5)
                    yield chunk
                    if chunk.get("type") in ("done", "error"):
                        break

                await producer_task
            except asyncio.TimeoutError:
                yield {"type": "error", "message": "stream consumer timed out"}
            finally:
                self._subscribers[session_id].remove(queue)
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]

    async def _produce(
        self,
        session_id: str,
        tool: str,
        input_data: dict,
        cid: int,
        tcp_addr: str,
    ) -> None:
        """Pull chunks from the VM and broadcast to all session subscribers."""
        async for chunk in stream_execute(
            tool=tool,
            input_data=input_data,
            cid=cid,
            tcp_addr=tcp_addr,
            timeout=self._max_timeout,
            buffer_size=self._buffer_size,
        ):
            for q in list(self._subscribers.get(session_id, [])):
                await q.put(chunk)

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, []))
