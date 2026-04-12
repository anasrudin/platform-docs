"""VMLifecycleManager — thin coordination layer over VMPool.

Wraps the VMPool with a cleaner interface for acquire/release/drain,
and wires it to the SnapshotDownloader so pool warmup uses the
BlobStore adapter instead of direct MinIO calls.

In FC_MODE=sim, the real pool is skipped and a _SimVM is returned from
acquire() so that ExecutionService can run without a firecracker binary.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid

import structlog

from orchestrator.snapshot import SnapshotDownloader, SnapshotPaths
from runtime.firecracker import VMPool, GuestResponse, detect_mode
from adapters.storage.base import BlobStore
from adapters.tracing import get_tracer

log = structlog.get_logger()


# ── Sim-mode VM ────────────────────────────────────────────────────────────────

class _SimVM:
    """Mock VM returned by VMLifecycleManager.acquire() in FC_MODE=sim.

    Implements the same .execute(tool, input_data) interface as FirecrackerVM
    without starting a real Firecracker process.
    """

    def execute(self, tool: str, input_data: dict) -> GuestResponse:
        time.sleep(0.05)
        tool_output = self._tool_output(tool, input_data)
        stdout = json.dumps({
            "tool": tool,
            "status": "completed",
            "runtime": "firecracker-sim",
            "vm_id": f"fc-sim-{uuid.uuid4().hex[:8]}",
            "output": tool_output,
            "sim_note": "FC_MODE=sim — no real VM",
        }, indent=2)
        return GuestResponse(exit_code=0, stdout=stdout, stderr="")

    def destroy(self) -> None:
        pass

    @staticmethod
    def _tool_output(tool: str, input_data: dict) -> object:
        if tool == "python_run":
            code = input_data.get("code", "print('hello from Python')")
            return {"stdout": f"[sim] {code}\n=> hello from Python", "exit_code": 0}
        if tool == "bash_run":
            cmd = input_data.get("command", "")
            return {"stdout": f"[sim] $ {cmd}\n=> command executed", "exit_code": 0}
        return f"[sim] {tool} executed with input: {input_data}"


class VMLifecycleManager:
    def __init__(
        self,
        storage: BlobStore | None,
        snapshot_name: str,
        pool_size: int,
        firecracker_bin: str,
        dev_mode: bool,
        cache_dir: str | None = None,
    ) -> None:
        self._cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "platform-snapshots")
        self._downloader = SnapshotDownloader(storage, self._cache_dir) if storage is not None else None
        self._snapshot_name = snapshot_name
        self._pool_size = pool_size
        self._firecracker_bin = firecracker_bin
        self._dev_mode = dev_mode
        self._pool: VMPool | None = None
        self._sim_mode: bool = False
        self._warmup_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the VM pool in a background thread.

        In FC_MODE=sim (or when /dev/kvm is absent), skip pool warmup entirely
        and return _SimVM instances from acquire() instead.

        In real mode, pool warmup runs in a background thread so the app starts
        up and becomes healthy immediately.  If the snapshot is not yet in MinIO,
        warmup will fail with a logged error but will not crash the process —
        acquire() calls will raise TimeoutError until the pool is populated.
        Upload the snapshot to MinIO and restart, or call warmup() directly once
        the snapshot is available.
        """
        mode = detect_mode()
        if mode == "sim":
            self._sim_mode = True
            log.info("vm lifecycle: sim mode, skipping pool warmup",
                     pool_size=self._pool_size, snapshot=self._snapshot_name)
            return

        if self._downloader is None:
            raise RuntimeError(
                "VMLifecycleManager started in real mode but storage=None. "
                "Pass a BlobStore implementation to enable snapshot download."
            )

        self._sim_mode = False
        _store = _DownloaderAdapter(self._downloader)
        self._pool = VMPool(
            pool_size=self._pool_size,
            snapshot_name=self._snapshot_name,
            snapshot_cache_dir=self._cache_dir,
            firecracker_bin=self._firecracker_bin,
            dev_mode=self._dev_mode,
            store=_store,
        )
        log.info("vm pool warming up in background",
                 pool_size=self._pool_size, snapshot=self._snapshot_name)
        self._warmup_thread = threading.Thread(target=self._warmup_bg, daemon=True,
                                               name="vm-pool-warmup")
        self._warmup_thread.start()

    def _warmup_bg(self) -> None:
        """Background warmup — logs errors but never raises."""
        try:
            self._pool.warmup()
            log.info("vm pool ready", pool_size=self._pool_size, snapshot=self._snapshot_name)
        except Exception as exc:
            log.error(
                "vm pool warmup failed — pool empty until snapshot is available and service restarts",
                err=str(exc),
                snapshot=self._snapshot_name,
                hint="upload snapshot via tools/snapshot-builder/ then restart platform-api",
            )

    def acquire(self, timeout: float = 30.0):
        if getattr(self, "_sim_mode", False):
            return _SimVM()
        if self._pool is None:
            raise RuntimeError("VMLifecycleManager not started")
        tracer = get_tracer()
        with tracer.start_span("pool.acquire", {
            "pool_size": self._pool_size,
            "snapshot_name": self._snapshot_name,
            "timeout_s": timeout,
        }) as span:
            vm = self._pool.acquire(timeout=timeout)
            if hasattr(self._pool, "available"):
                span.set_attribute("pool_available", self._pool.available)
            return vm

    def release(self, vm) -> None:
        if isinstance(vm, _SimVM):
            return
        if self._pool is not None:
            self._pool.release(vm)

    def stop(self) -> None:
        if self._pool is not None:
            self._pool.drain()
            self._pool = None
            log.info("vm pool drained")


class _DownloaderAdapter:
    """Adapts SnapshotDownloader to the SnapshotStore interface expected by VMPool."""

    def __init__(self, downloader: SnapshotDownloader) -> None:
        self._dl = downloader

    def ensure(self, name: str) -> SnapshotPaths:
        return self._dl.ensure(name)
