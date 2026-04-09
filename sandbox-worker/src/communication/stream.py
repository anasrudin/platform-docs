"""Streaming output transport — async generator that reads stdout chunks from vsock/TCP.

Layer 5 (Communication): handles the wire-level streaming protocol.
Each yielded chunk is a dict ready to serialize as JSON to the WebSocket client.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from adapters.tracing import get_tracer


async def stream_execute(
    tool: str,
    input_data: dict,
    cid: int = 0,
    tcp_addr: str = "",
    timeout: float = 300.0,
    buffer_size: int = 4096,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream stdout/stderr chunks from a VM guest as async generator.

    Yields dicts:
        {"type": "stdout", "data": "...", "ts": "..."}
        {"type": "stderr", "data": "...", "ts": "..."}
        {"type": "done",   "exit_code": 0, "duration_ms": 123}
        {"type": "error",  "message": "..."}  ← on timeout / transport error
    """
    tracer = get_tracer()
    start = time.monotonic()

    with tracer.start_span("communication.stream.execute", {"tool": tool, "timeout": timeout}):
        try:
            async for chunk in _do_stream(tool, input_data, cid, tcp_addr, timeout, buffer_size):
                yield chunk
        except asyncio.TimeoutError:
            yield {"type": "error", "message": f"execution timed out after {timeout}s"}
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            yield {"type": "done", "exit_code": 0, "duration_ms": duration_ms}


async def _do_stream(
    tool: str,
    input_data: dict,
    cid: int,
    tcp_addr: str,
    timeout: float,
    buffer_size: int,
) -> AsyncGenerator[dict[str, Any], None]:
    """Inner streaming — opens connection and yields output chunks."""
    import asyncio
    loop = asyncio.get_event_loop()

    # Build the request message
    payload = json.dumps({"tool": tool, "input": input_data, "stream": True}).encode()
    msg = (f"POST /execute/stream HTTP/1.0\nContent-Length: {len(payload)}\n\n").encode() + payload

    # Connect via TCP or vsock
    if tcp_addr:
        host, port = tcp_addr.rsplit(":", 1)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)), timeout=5.0
        )
    else:
        # vsock via asyncio (Linux only)
        reader, writer = await asyncio.wait_for(
            _open_vsock_connection(cid, 8080), timeout=5.0
        )

    try:
        writer.write(msg)
        writer.write_eof()
        await writer.drain()

        ts = _now_iso()
        async with asyncio.timeout(timeout):
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    chunk = json.loads(line.decode().strip())
                    chunk.setdefault("ts", ts)
                    yield chunk
                except json.JSONDecodeError:
                    # Raw stdout line (non-JSON guest)
                    yield {"type": "stdout", "data": line.decode(), "ts": ts}
    finally:
        writer.close()


async def _open_vsock_connection(cid: int, port: int):
    """Open an AF_VSOCK stream as asyncio reader/writer (Linux only)."""
    import socket
    try:
        AF_VSOCK = socket.AF_VSOCK  # type: ignore[attr-defined]
    except AttributeError as exc:
        raise OSError("AF_VSOCK not available (Linux only)") from exc

    loop = asyncio.get_event_loop()
    sock = socket.socket(AF_VSOCK, socket.SOCK_STREAM)
    sock.setblocking(False)
    await loop.sock_connect(sock, (cid, port))
    return await asyncio.open_connection(sock=sock)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
