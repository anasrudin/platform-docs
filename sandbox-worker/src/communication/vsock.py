"""vsock transport — low-level AF_VSOCK connection for FC guest communication.

Layer 5 (Communication): handles the socket-level send/recv only.
The GuestClient in communication/guest.py uses this for actual calls.
"""
from __future__ import annotations

import socket


VSOCK_UNAVAILABLE_MSG = "AF_VSOCK not available on this platform (Linux only)"


def dial_vsock(cid: int, port: int, timeout: float = 3.0) -> socket.socket:
    """Open a vsock connection to a Firecracker VM guest.

    Raises OSError on non-Linux platforms where AF_VSOCK is absent.
    """
    try:
        AF_VSOCK = socket.AF_VSOCK  # type: ignore[attr-defined]
    except AttributeError as exc:
        raise OSError(VSOCK_UNAVAILABLE_MSG) from exc

    sock = socket.socket(AF_VSOCK, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((cid, port))
    return sock


def dial_tcp(host: str, port: int, timeout: float = 3.0) -> socket.socket:
    """Open a TCP connection (dev/test fallback when vsock unavailable)."""
    return socket.create_connection((host, port), timeout=timeout)
