"""Artifact upload/download via MinIO with local filesystem fallback.

Mirrors internal/artifacts/store.go.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import structlog

log = structlog.get_logger()


class Config:
    """MinIO connection settings, read from environment."""

    def __init__(
        self,
        endpoint: str = "http://localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket: str = "platform-artifacts",
        local_dir: str = "",
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.local_dir = local_dir

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            endpoint=_env_or("MINIO_ENDPOINT", "http://localhost:9000"),
            access_key=_env_or("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=_env_or("MINIO_SECRET_KEY", "minioadmin"),
            bucket=_env_or("MINIO_ARTIFACTS_BUCKET", "platform-artifacts"),
            local_dir=_env_or("ARTIFACTS_LOCAL_DIR", ""),
        )


class Store:
    """Handles artifact upload and download against a MinIO bucket."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def upload(self, artifact_id: str, name: str, src: io.IOBase) -> str:
        """Write src to MinIO at <bucket>/<artifact_id>/<name>.

        Returns the MinIO key on success.
        """
        key = f"{artifact_id}/{name}"

        if self._cfg.local_dir:
            self._write_local(key, src)
            log.info(
                "artifact uploaded to local store", key=key, dir=self._cfg.local_dir
            )
            return key

        # Buffer to a temp file, then push via mc.
        with tempfile.NamedTemporaryFile(prefix="artifact-", delete=False) as tmp:
            shutil.copyfileobj(src, tmp)
            tmp_path = tmp.name

        try:
            self._push_to_minio(tmp_path, key)
        finally:
            os.unlink(tmp_path)

        log.info("artifact uploaded", key=key, bucket=self._cfg.bucket)
        return key

    def download(self, key: str, dst: io.IOBase) -> None:
        """Fetch an artifact by key and write it to dst."""
        if self._cfg.local_dir:
            self._read_local(key, dst)
            return

        with tempfile.NamedTemporaryFile(prefix="artifact-dl-", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            try:
                self._pull_from_minio(key, tmp_path)
            except Exception as mc_err:
                log.warning("mc pull failed, trying HTTP fallback", err=str(mc_err))
                url = f"{self._cfg.endpoint}/{self._cfg.bucket}/{key}"
                self._http_get(url, tmp_path)

            with open(tmp_path, "rb") as f:
                shutil.copyfileobj(f, dst)
        finally:
            os.unlink(tmp_path)

    def url(self, key: str) -> str:
        """Return the direct MinIO URL for an artifact key."""
        if self._cfg.local_dir:
            return f"/artifacts/{key}"
        return f"{self._cfg.endpoint}/{self._cfg.bucket}/{key}"

    def ensure_bucket(self) -> None:
        """Create the artifact bucket if it does not exist."""
        if self._cfg.local_dir:
            ensure_local_dir(self._cfg.local_dir)
            return

        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")

        alias = f"art-init-{int(time.time() * 1e9)}"
        subprocess.run(
            [
                mc,
                "alias",
                "set",
                alias,
                self._cfg.endpoint,
                self._cfg.access_key,
                self._cfg.secret_key,
                "--quiet",
            ],
            check=True,
            capture_output=True,
        )
        try:
            subprocess.run(
                [
                    mc,
                    "mb",
                    "--ignore-existing",
                    "--quiet",
                    f"{alias}/{self._cfg.bucket}",
                ],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)

    # ── MinIO helpers ──────────────────────────────────────────────────────────

    def _mc_alias(self) -> tuple[str, str]:
        """Ensure mc is available and create a temporary alias. Returns (mc_path, alias)."""
        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")
        alias = f"art-{int(time.time() * 1e9)}"
        subprocess.run(
            [
                mc,
                "alias",
                "set",
                alias,
                self._cfg.endpoint,
                self._cfg.access_key,
                self._cfg.secret_key,
                "--quiet",
            ],
            check=True,
            capture_output=True,
        )
        return mc, alias

    def _push_to_minio(self, local_path: str, key: str) -> None:
        mc, alias = self._mc_alias()
        try:
            subprocess.run(
                [mc, "cp", "--quiet", local_path, f"{alias}/{self._cfg.bucket}/{key}"],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)

    def _pull_from_minio(self, key: str, dest: str) -> None:
        mc, alias = self._mc_alias()
        try:
            subprocess.run(
                [mc, "cp", "--quiet", f"{alias}/{self._cfg.bucket}/{key}", dest],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)

    def _http_get(self, url: str, dest: str) -> None:
        import urllib.request

        with urllib.request.urlopen(url) as resp:  # noqa: S310
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)

    # ── Local dir helpers ──────────────────────────────────────────────────────

    def _write_local(self, key: str, src: io.IOBase) -> None:
        path = local_path(self._cfg.local_dir, key)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            shutil.copyfileobj(src, f)

    def _read_local(self, key: str, dst: io.IOBase) -> None:
        path = local_path(self._cfg.local_dir, key)
        with open(path, "rb") as f:
            shutil.copyfileobj(f, dst)


# ── Module-level helpers ───────────────────────────────────────────────────────


def mc_available() -> bool:
    """Report whether the MinIO client is available in PATH."""
    return shutil.which("mc") is not None


def ensure_local_dir(directory: str) -> None:
    """Create a local directory to simulate an artifact store."""
    Path(directory).mkdir(parents=True, exist_ok=True)


def local_path(base_dir: str, key: str) -> str:
    """Return the local filesystem path for an artifact."""
    return str(Path(base_dir) / Path(key))


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key, default) or default
