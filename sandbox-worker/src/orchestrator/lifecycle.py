"""VMLifecycleManager — thin coordination layer over VMPool.

Wraps the VMPool with a cleaner interface for acquire/release/drain,
and wires it to the SnapshotDownloader so pool warmup uses the
BlobStore adapter instead of direct MinIO calls.
"""
from __future__ import annotations

import os
import tempfile

import structlog

from orchestrator.snapshot import SnapshotDownloader, SnapshotPaths
from runtime.firecracker import VMPool
from adapters.storage.base import BlobStore

log = structlog.get_logger()


class VMLifecycleManager:
    def __init__(
        self,
        storage: BlobStore,
        snapshot_name: str,
        pool_size: int,
        firecracker_bin: str,
        dev_mode: bool,
        cache_dir: str | None = None,
    ) -> None:
        self._cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "platform-snapshots")
        self._downloader = SnapshotDownloader(storage, self._cache_dir)
        self._snapshot_name = snapshot_name
        self._pool_size = pool_size
        self._firecracker_bin = firecracker_bin
        self._dev_mode = dev_mode
        self._pool: VMPool | None = None

    def start(self) -> None:
        """Download the snapshot and warm the VM pool."""
        # Use the downloader as a drop-in replacement for SnapshotStore
        # VMPool still takes SnapshotStore; we pass a wrapper that adapts
        _store = _DownloaderAdapter(self._downloader)
        self._pool = VMPool(
            pool_size=self._pool_size,
            snapshot_name=self._snapshot_name,
            snapshot_cache_dir=self._cache_dir,
            firecracker_bin=self._firecracker_bin,
            dev_mode=self._dev_mode,
            store=_store,
        )
        log.info("vm pool warming up", pool_size=self._pool_size, snapshot=self._snapshot_name)
        self._pool.warmup()
        log.info("vm pool ready")

    def acquire(self, timeout: float = 30.0):
        if self._pool is None:
            raise RuntimeError("VMLifecycleManager not started")
        return self._pool.acquire(timeout=timeout)

    def release(self, vm) -> None:
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
