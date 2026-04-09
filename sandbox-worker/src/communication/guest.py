"""GuestClient — communicates with the agent inside a Firecracker VM.

Layer 5 (Communication): owns the wire protocol (JSON-over-vsock/TCP).
Orchestrator calls this to send jobs; it doesn't know about pools or tiers.
"""
from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass

from adapters.tracing import get_tracer
from communication.vsock import dial_tcp, dial_vsock

GUEST_AGENT_PORT = 8080


def _dial_vsock(cid: int, port: int) -> "socket.socket":
    """Compat shim — delegates to communication.vsock.dial_vsock."""
    return dial_vsock(cid, port)


@dataclass
class GuestRequest:
    tool: str
    input: dict


@dataclass
class GuestResponse:
    exit_code: int
    stdout: str
    stderr: str


class GuestClient:
    """Sends tool execution requests to a running Firecracker guest."""

    def __init__(
        self,
        cid: int,
        tcp_addr: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._cid = cid
        self._port = GUEST_AGENT_PORT
        self._tcp_addr = tcp_addr   # non-empty → TCP fallback (dev/macOS)
        self._timeout = timeout

    def execute(self, tool: str, input_data: dict) -> GuestResponse:
        """Send a tool execution request and return the guest's response."""
        tracer = get_tracer()
        transport = "tcp" if self._tcp_addr else "vsock"

        with tracer.start_span("communication.vsock.execute", {
            "tool": tool,
            "input_size": len(json.dumps(input_data)),
            "transport": transport,
            "cid": self._cid,
        }) as span:
            payload = json.dumps({"tool": tool, "input": input_data}).encode()
            msg = (f"POST /execute HTTP/1.0\nContent-Length: {len(payload)}\n\n").encode() + payload

            conn = self._dial()
            try:
                conn.settimeout(self._timeout)
                conn.sendall(msg)
                conn.shutdown(socket.SHUT_WR)
                raw = b""
                while chunk := conn.recv(4096):
                    raw += chunk
            finally:
                conn.close()

            data = json.loads(raw.rstrip(b"\n").decode())
            resp = GuestResponse(
                exit_code=data.get("exit_code", 0),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
            )
            span.set_attribute("exit_code", resp.exit_code)
            return resp

    def wait_ready(self, timeout: float = 15.0) -> None:
        """Poll until the guest agent accepts connections."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                conn = self._dial()
                conn.close()
                return
            except OSError:
                time.sleep(0.1)
        raise TimeoutError(f"guest agent not ready after {timeout}s")

    def _dial(self) -> socket.socket:
        if self._tcp_addr:
            host, port = self._tcp_addr.rsplit(":", 1)
            return dial_tcp(host, int(port))
        return dial_vsock(self._cid, self._port)
