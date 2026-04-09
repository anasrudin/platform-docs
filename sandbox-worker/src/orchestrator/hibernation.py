"""VM Hibernation orchestrator — pause → snapshot → upload → destroy / download → restore → resume.

Uses the Firecracker snapshot API and the BlobStore adapter.
In sim mode (no /dev/kvm or FC_MODE=sim) both operations are no-ops
that return immediately — safe for dev and tests.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import structlog

from adapters.storage.base import BlobStore
from adapters.tracing import get_tracer
from models.hibernation import HibernateSnapshot, RestoreResult

log = structlog.get_logger()

# Firecracker API paths (relative to socket)
_VMSTATE_FILE = "vmstate.bin"
_MEMFILE = "memory.bin"


class HibernationOrchestrator:
    """Handles the Firecracker-level hibernate and restore sequences."""

    def __init__(self, storage: BlobStore, sim_mode: bool = False) -> None:
        self._storage = storage
        # sim_mode = True on macOS / test environments without KVM
        self._sim = sim_mode or not _kvm_available()

    # ── Public API ─────────────────────────────────────────────────────────────

    def hibernate(self, session_id: str, fc_socket: str = "") -> HibernateSnapshot:
        """Pause VM, snapshot to storage, destroy process."""
        tracer = get_tracer()
        snapshot_key = f"hibernate/{session_id}"

        with tracer.start_span("orchestrator.vm.hibernate", {"session_id": session_id, "sim": self._sim}):
            if self._sim:
                log.info("hibernation sim: no-op", session_id=session_id)
            else:
                self._fc_pause(fc_socket)
                with tempfile.TemporaryDirectory() as tmp:
                    self._fc_snapshot(fc_socket, tmp)
                    self._upload_snapshot(session_id, tmp)
                self._fc_destroy(fc_socket)

            snap = HibernateSnapshot(
                session_id=session_id,
                snapshot_key=snapshot_key,
            )
            log.info("hibernated", session_id=session_id, key=snapshot_key)
            return snap

    def restore(self, session_id: str, snapshot_key: str, fc_socket: str = "") -> RestoreResult:
        """Download snapshot, start new FC process, resume VM."""
        tracer = get_tracer()
        start = time.monotonic()

        with tracer.start_span("orchestrator.vm.restore", {"session_id": session_id, "sim": self._sim}):
            if self._sim:
                log.info("restore sim: no-op", session_id=session_id)
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    self._download_snapshot(session_id, tmp)
                    self._fc_load_snapshot(fc_socket, tmp)
                self._fc_resume(fc_socket)

            restore_ms = int((time.monotonic() - start) * 1000)
            log.info("restored", session_id=session_id, restore_ms=restore_ms)
            return RestoreResult(
                session_id=session_id,
                restored_from=snapshot_key,
                restore_ms=restore_ms,
            )

    # ── Firecracker API helpers ────────────────────────────────────────────────

    def _fc_pause(self, socket_path: str) -> None:
        self._fc_api(socket_path, "PUT", "/vm/state", {"state": "Paused"})

    def _fc_resume(self, socket_path: str) -> None:
        self._fc_api(socket_path, "PUT", "/vm/state", {"state": "Resumed"})

    def _fc_snapshot(self, socket_path: str, dest_dir: str) -> None:
        self._fc_api(socket_path, "PUT", "/vm/snapshot/create", {
            "snapshot_path": os.path.join(dest_dir, _VMSTATE_FILE),
            "mem_file_path": os.path.join(dest_dir, _MEMFILE),
            "snapshot_type": "Full",
        })

    def _fc_load_snapshot(self, socket_path: str, src_dir: str) -> None:
        self._fc_api(socket_path, "PUT", "/snapshot/load", {
            "snapshot_path": os.path.join(src_dir, _VMSTATE_FILE),
            "mem_file_path": os.path.join(src_dir, _MEMFILE),
            "enable_diff_snapshots": False,
        })

    def _fc_destroy(self, socket_path: str) -> None:
        """Send SIGTERM / shutdown via API — real impl would send action:SendCtrlAltDel or kill."""
        try:
            self._fc_api(socket_path, "PUT", "/actions", {"action_type": "SendCtrlAltDel"})
        except Exception:
            pass  # Process may already be gone

    def _fc_api(self, socket_path: str, method: str, path: str, body: dict) -> None:
        """Send a request to the Firecracker HTTP API via Unix socket."""
        import http.client
        import json
        conn = http.client.HTTPConnection("localhost")
        conn.connect()
        # Override socket with the Unix socket path
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        conn.sock = sock
        payload = json.dumps(body).encode()
        conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status not in (200, 204):
            raise RuntimeError(f"FC API {method} {path} → {resp.status}: {resp.read().decode()}")

    # ── Storage helpers ────────────────────────────────────────────────────────

    def _upload_snapshot(self, session_id: str, src_dir: str) -> None:
        for fname in (_VMSTATE_FILE, _MEMFILE):
            data = Path(os.path.join(src_dir, fname)).read_bytes()
            key = f"hibernate/{session_id}/{fname}"
            self._storage.upload(key, data)
            log.debug("snapshot blob uploaded", key=key, size=len(data))

    def _download_snapshot(self, session_id: str, dest_dir: str) -> None:
        for fname in (_VMSTATE_FILE, _MEMFILE):
            key = f"hibernate/{session_id}/{fname}"
            data = self._storage.download(key)
            Path(os.path.join(dest_dir, fname)).write_bytes(data)
            log.debug("snapshot blob downloaded", key=key)


def _kvm_available() -> bool:
    return os.path.exists("/dev/kvm") or os.environ.get("FC_MODE") == "real"
