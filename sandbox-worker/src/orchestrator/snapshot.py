"""SnapshotDownloader — pulls FC snapshots via the BlobStore adapter.

Replaces the direct mc/HTTP download in sandbox_platform.runtime.firecracker.snapshot
with the cloud-agnostic BlobStore protocol, so snapshots can live in MinIO,
S3, GCS, or local filesystem without code changes.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from adapters.storage.base import BlobStore
from adapters.tracing import get_tracer

log = structlog.get_logger()


@dataclass
class SnapshotMeta:
    name: str = ""
    version: str = ""
    kernel: str = ""
    rootfs: str = ""
    vcpus: int = 2
    mem_mib: int = 512
    created_at: datetime = field(default_factory=datetime.utcnow)
    dry_run: bool = False
    files: dict[str, str] = field(default_factory=dict)


@dataclass
class SnapshotPaths:
    state_file: str
    mem_file: str
    meta_file: str
    meta: SnapshotMeta = field(default_factory=SnapshotMeta)


class SnapshotDownloader:
    """Downloads and caches FC snapshots via any BlobStore adapter."""

    _BLOBS = ("vmstate.bin", "memory.bin", "meta.json")

    def __init__(self, storage: BlobStore, cache_dir: str) -> None:
        self._storage = storage
        self._cache_dir = cache_dir

    def ensure(self, name: str) -> SnapshotPaths:
        """Return local paths for the named snapshot, downloading if needed."""
        tracer = get_tracer()
        start = time.monotonic()
        with tracer.start_span("vm.restore_snapshot", {"snapshot_name": name}) as span:
            local_dir = os.path.join(self._cache_dir, name)
            paths = SnapshotPaths(
                state_file=os.path.join(local_dir, "vmstate.bin"),
                mem_file=os.path.join(local_dir, "memory.bin"),
                meta_file=os.path.join(local_dir, "meta.json"),
            )

            if self._all_exist(paths.state_file, paths.mem_file, paths.meta_file):
                log.debug("snapshot cache hit", name=name)
                result = self._load_meta(paths)
                span.set_attribute("cache_hit", True)
                span.set_attribute("duration_ms", int((time.monotonic() - start) * 1000))
                return result

            log.info("snapshot not cached, downloading via BlobStore", name=name)
            Path(local_dir).mkdir(parents=True, exist_ok=True)

            for blob in self._BLOBS:
                key = f"{name}/{blob}"
                dest = os.path.join(local_dir, blob)
                data = self._storage.download(key)
                Path(dest).write_bytes(data)
                log.debug("snapshot blob downloaded", key=key, dest=dest)

            span.set_attribute("cache_hit", False)
            span.set_attribute("duration_ms", int((time.monotonic() - start) * 1000))
            return self._load_meta(paths)

    def upload(self, name: str, local_dir: str) -> None:
        """Upload all snapshot blobs from local_dir under <name>/ prefix."""
        for blob in self._BLOBS:
            src = os.path.join(local_dir, blob)
            data = Path(src).read_bytes()
            key = f"{name}/{blob}"
            self._storage.upload(key, data)
            log.info("snapshot blob uploaded", key=key, size=len(data))

    def _load_meta(self, paths: SnapshotPaths) -> SnapshotPaths:
        with open(paths.meta_file) as f:
            data = json.load(f)
        paths.meta = SnapshotMeta(
            name=data.get("name", ""),
            version=data.get("version", ""),
            kernel=data.get("kernel", ""),
            rootfs=data.get("rootfs", ""),
            vcpus=data.get("vcpus", 2),
            mem_mib=data.get("mem_mib", 512),
            dry_run=data.get("dry_run", False),
            files=data.get("files", {}),
        )
        return paths

    @staticmethod
    def _all_exist(*files: str) -> bool:
        return all(os.path.exists(f) for f in files)
