"""Unit tests for sandbox_platform.runtime.firecracker.guest.

Mirrors vsock_linux.go / vsock_stub.go behaviour:
- On Linux with AF_VSOCK: real vsock dial
- On macOS / no AF_VSOCK: raises OSError (stub)
"""
import socket
import sys

import pytest

from sandbox_platform.runtime.firecracker.guest import (
    GUEST_AGENT_PORT,
    GuestClient,
    GuestResponse,
    _dial_vsock,
)


class TestGuestConstants:
    def test_guest_agent_port(self):
        assert GUEST_AGENT_PORT == 8080


class TestDialVsock:
    def test_vsock_unavailable_on_non_linux(self):
        """Mirrors vsock_stub.go: dialVsock returns error on non-Linux."""
        if not hasattr(socket, "AF_VSOCK"):
            with pytest.raises(OSError, match="AF_VSOCK not available"):
                _dial_vsock(cid=3, port=8080)
        else:
            # On Linux, AF_VSOCK exists — connection may still fail if no VM running,
            # but the function should try (not raise AttributeError).
            try:
                conn = _dial_vsock(cid=99999, port=8080)
                conn.close()
            except OSError:
                pass  # expected: no VM with that CID


class TestGuestClient:
    def test_init_with_tcp_addr(self):
        client = GuestClient(cid=3, tcp_addr="127.0.0.1:8080", timeout=5.0)
        assert client._cid == 3
        assert client._tcp_addr == "127.0.0.1:8080"
        assert client._timeout == 5.0

    def test_init_without_tcp_addr(self):
        client = GuestClient(cid=5)
        assert client._tcp_addr == ""
        assert client._port == GUEST_AGENT_PORT

    def test_wait_ready_times_out_when_no_server(self):
        """wait_ready should raise TimeoutError when no server is listening."""
        client = GuestClient(cid=3, tcp_addr="127.0.0.1:19999", timeout=30.0)
        with pytest.raises(TimeoutError, match="not ready"):
            client.wait_ready(timeout=0.2)  # very short timeout

    def test_execute_fails_when_no_server(self):
        """execute should raise OSError/ConnectionRefusedError when no server."""
        client = GuestClient(cid=3, tcp_addr="127.0.0.1:19999", timeout=1.0)
        with pytest.raises(OSError):
            client.execute("echo", {"x": 1})
