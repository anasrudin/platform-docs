"""BlobStore adapter for Firecracker snapshots.

This wraps the existing S3-compatible MinIO client so the snapshot downloader
can use the same bucket layout as fc-agent and the runbook assets:
<snapshot_name>/<blob>.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import time
from pathlib import Path

from adapters.storage.s3_compat import Config as S3Config, Store as S3Store


class SnapshotBlobStore:
    """BlobStore implementation backed by the existing S3-compatible store."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        local_dir: str = "",
    ) -> None:
        self._cfg = S3Config(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            local_dir=local_dir,
        )
        self._store = S3Store(self._cfg)

    def ensure_bucket(self) -> None:
        self._store.ensure_bucket()

    def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        snapshot_name, blob_name = self._split_key(key)
        return self._store.upload(snapshot_name, blob_name, io.BytesIO(data))

    def download(self, key: str) -> bytes:
        buf = io.BytesIO()
        self._store.download(key, buf)
        return buf.getvalue()

    def delete(self, key: str) -> None:
        if self._cfg.local_dir:
            path = Path(self._cfg.local_dir) / key
            if path.exists():
                path.unlink()
            return

        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")

        alias = f"snap-{int(time.time() * 1e9)}"
        subprocess.run(
            [mc, "alias", "set", alias, self._cfg.endpoint,
             self._cfg.access_key, self._cfg.secret_key, "--quiet"],
            check=True,
            capture_output=True,
        )
        try:
            subprocess.run(
                [mc, "rm", "--force", f"{alias}/{self._cfg.bucket}/{key}"],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)

    def exists(self, key: str) -> bool:
        if self._cfg.local_dir:
            return (Path(self._cfg.local_dir) / key).exists()
        try:
            self.download(key)
            return True
        except Exception:
            return False

    def public_url(self, key: str) -> str:
        return self._store.url(key)

    @staticmethod
    def _split_key(key: str) -> tuple[str, str]:
        if "/" not in key:
            raise ValueError("snapshot key must be in <snapshot>/<blob> form")
        return key.split("/", 1)

