"""Guest agent client for Firecracker microVMs.

Mirrors runtime/firecracker/guest.go.
Communication is via vsock (Linux) or TCP (dev/test mode).
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass

GUEST_AGENT_PORT = 8080


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
    """Communicates with the agent inside a Firecracker VM."""

    def __init__(
        self,
        cid: int,
        tcp_addr: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._cid = cid
        self._port = GUEST_AGENT_PORT
        self._tcp_addr = tcp_addr  # non-empty → TCP fallback (dev mode)
        self._timeout = timeout

    def execute(self, tool: str, input_data: dict) -> GuestResponse:
        """Send a tool execution request to the guest and return the result."""
        payload = json.dumps({"tool": tool, "input": input_data}).encode()
        msg = (
            f"POST /execute HTTP/1.0\nContent-Length: {len(payload)}\n\n"
        ).encode() + payload

        conn = self._dial()
        try:
            conn.settimeout(self._timeout)
            conn.sendall(msg)
            # Signal end of send so guest knows to start reading
            conn.shutdown(socket.SHUT_WR)
            raw = b""
            while chunk := conn.recv(4096):
                raw += chunk
        finally:
            conn.close()

        body = raw.rstrip(b"\n").decode()
        data = json.loads(body)
        return GuestResponse(
            exit_code=data.get("exit_code", 0),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
        )

    def wait_ready(self, timeout: float = 15.0) -> None:
        """Poll guest agent until it accepts connections (or timeout)."""
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
            sock = socket.create_connection((host, int(port)), timeout=3.0)
            return sock
        return _dial_vsock(self._cid, self._port)


def _dial_vsock(cid: int, port: int) -> socket.socket:
    """Open a vsock connection. Only works on Linux with AF_VSOCK."""
    try:
        AF_VSOCK = socket.AF_VSOCK  # type: ignore[attr-defined]
    except AttributeError as exc:
        raise OSError("AF_VSOCK not available on this platform (not Linux)") from exc
    sock = socket.socket(AF_VSOCK, socket.SOCK_STREAM)
    sock.connect((cid, port))
    return sock
