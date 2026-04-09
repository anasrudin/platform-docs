"""Firecracker snapshot store: download and cache snapshots from MinIO.

Mirrors runtime/firecracker/snapshot.go.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

log = structlog.get_logger()


@dataclass
class SnapshotMeta:
    """Mirrors the meta.json written by snapshot-builder.sh."""

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


class SnapshotStore:
    """Downloads and caches snapshots from MinIO.

    On cache hit returns immediately; on miss pulls via `mc` CLI or HTTP.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        cache_dir: str,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._cache_dir = cache_dir

    def ensure(self, name: str) -> SnapshotPaths:
        """Return local paths for the named snapshot, downloading if needed."""
        local_dir = os.path.join(self._cache_dir, name)
        paths = SnapshotPaths(
            state_file=os.path.join(local_dir, "vmstate.bin"),
            mem_file=os.path.join(local_dir, "memory.bin"),
            meta_file=os.path.join(local_dir, "meta.json"),
        )

        if self._all_exist(paths.state_file, paths.mem_file, paths.meta_file):
            log.debug("snapshot cache hit", name=name)
            return self._load_meta(paths)

        log.info("snapshot not cached, downloading from MinIO", name=name)
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        try:
            self._pull_from_minio(f"{self._bucket}/{name}/", local_dir)
        except Exception as mc_err:
            log.warning("mc pull failed, trying HTTP download", err=str(mc_err))
            self._http_download(name, paths)

        return self._load_meta(paths)

    def _pull_from_minio(self, prefix: str, dest_dir: str) -> None:
        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")
        alias = f"fc-dl-{int(time.time() * 1e9)}"
        subprocess.run(
            [
                mc,
                "alias",
                "set",
                alias,
                self._endpoint,
                self._access_key,
                self._secret_key,
                "--quiet",
            ],
            check=True,
            capture_output=True,
        )
        try:
            subprocess.run(
                [mc, "mirror", "--quiet", f"{alias}/{prefix}", dest_dir],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)

    def _http_download(self, name: str, paths: SnapshotPaths) -> None:
        base = f"{self._endpoint}/{self._bucket}/{name}"
        files = {
            f"{base}/vmstate.bin": paths.state_file,
            f"{base}/memory.bin": paths.mem_file,
            f"{base}/meta.json": paths.meta_file,
        }
        for url, dest in files.items():
            _download_file(url, dest)

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


def _download_file(url: str, dest: str) -> None:
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        with open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
