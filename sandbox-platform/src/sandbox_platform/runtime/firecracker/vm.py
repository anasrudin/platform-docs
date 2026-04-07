"""Firecracker VM lifecycle management.

Mirrors runtime/firecracker/vm.go.
Each VM is single-use: restored from snapshot, used once, then destroyed.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import structlog

from sandbox_platform.runtime.firecracker.guest import GuestClient, GuestResponse
from sandbox_platform.runtime.firecracker.snapshot import SnapshotPaths

log = structlog.get_logger()


class VMState(IntEnum):
    BOOTING = 0
    READY = 1
    BUSY = 2
    DESTROYED = 3


class FirecrackerVM:
    """A single Firecracker microVM instance."""

    def __init__(
        self,
        vm_id: str,
        cid: int,
        api_sock: str,
        log_path: str,
        snap: SnapshotPaths,
        process: subprocess.Popen,
        guest: GuestClient,
    ) -> None:
        self.id = vm_id
        self.cid = cid
        self._api_sock = api_sock
        self._log_path = log_path
        self._snap = snap
        self._process = process
        self._guest = guest
        self.state = VMState.READY
        self.booted_at = time.monotonic()

    def execute(self, tool: str, input_data: dict) -> GuestResponse:
        self.state = VMState.BUSY
        try:
            return self._guest.execute(tool, input_data)
        finally:
            self.state = VMState.READY

    def destroy(self) -> None:
        self.state = VMState.DESTROYED
        try:
            self._process.kill()
            self._process.wait(timeout=5)
        except Exception:
            pass
        for path in (self._api_sock, self._log_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        log.debug("vm destroyed", id=self.id)

    # ── Firecracker API ────────────────────────────────────────────────────────

    def _api_call(self, method: str, path: str, body: dict) -> None:
        data = json.dumps(body).encode()
        # Connect via Unix socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(10.0)
            sock.connect(self._api_sock)
            request = (
                f"{method} {path} HTTP/1.0\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(data)}\r\n\r\n"
            ).encode() + data
            sock.sendall(request)
            response = b""
            while chunk := sock.recv(4096):
                response += chunk
        status_line = response.split(b"\r\n", 1)[0]
        parts = status_line.split(b" ", 2)
        if len(parts) >= 2:
            code = int(parts[1])
            if code >= 300:
                raise RuntimeError(f"FC API {method} {path}: HTTP {code}")

    def _api_put(self, path: str, body: dict) -> None:
        self._api_call("PUT", path, body)

    def _api_patch(self, path: str, body: dict) -> None:
        self._api_call("PATCH", path, body)

    def _wait_for_socket(self, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if os.path.exists(self._api_sock):
                return
            time.sleep(0.05)
        raise TimeoutError(f"FC socket {self._api_sock} not ready after {timeout}s")

    def _restore(self, snap: SnapshotPaths, cid: int) -> None:
        try:
            self._api_put("/vsock", {
                "guest_cid": cid,
                "uds_path": f"/tmp/fc-vsock-{self.id}.sock",
            })
        except Exception as exc:
            log.warning("vsock setup failed (non-fatal in dev mode)", err=str(exc))

        self._api_put("/snapshot/load", {
            "snapshot_path": snap.state_file,
            "mem_file_path": snap.mem_file,
            "backend_type": "File",
            "enable_diff_snapshots": False,
        })


def new_vm(
    snap: SnapshotPaths,
    cid: int,
    work_dir: str,
    firecracker_bin: str,
    dev_mode: bool = False,
) -> FirecrackerVM:
    """Start a Firecracker process and restore from snapshot."""
    import uuid as _uuid
    vm_id = _uuid.uuid4().hex[:8]
    api_sock = os.path.join(work_dir, f"fc-{vm_id}.sock")
    log_path = os.path.join(work_dir, f"fc-{vm_id}.log")

    Path(work_dir).mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [firecracker_bin, "--api-sock", api_sock, "--log-path", log_path, "--level", "Error"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    guest_addr = f"127.0.0.1:{8080}" if dev_mode else ""
    guest = GuestClient(cid=cid, tcp_addr=guest_addr)

    vm = FirecrackerVM(
        vm_id=vm_id,
        cid=cid,
        api_sock=api_sock,
        log_path=log_path,
        snap=snap,
        process=proc,
        guest=guest,
    )

    vm._wait_for_socket(timeout=3.0)
    vm._restore(snap, cid)
    vm._api_patch("/vm", {"state": "Resumed"})

    guest.wait_ready(timeout=15.0)

    log.info("vm ready", id=vm_id, cid=cid, pid=proc.pid)
    return vm
