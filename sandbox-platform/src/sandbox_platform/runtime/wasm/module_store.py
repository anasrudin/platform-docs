"""WASM module store: download and cache .wasm modules from MinIO.

Mirrors runtime/wasm/module_store.go.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import structlog

log = structlog.get_logger()


class ModuleStore:
    """Downloads and caches .wasm modules from MinIO."""

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

    def ensure(self, tool: str) -> str:
        """Return the local path to <tool>.wasm, downloading if needed."""
        filename = f"{tool}.wasm"
        local_path = os.path.join(self._cache_dir, filename)

        if os.path.exists(local_path):
            log.debug("module cache hit", tool=tool)
            return local_path

        log.info("module not cached, downloading from MinIO", tool=tool)
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)

        key = f"{self._bucket}/{filename}"
        try:
            self._pull_from_minio(key, local_path)
        except Exception as mc_err:
            log.warning("mc pull failed, trying HTTP download", err=str(mc_err))
            url = f"{self._endpoint}/{self._bucket}/{filename}"
            _download_file(url, local_path)

        return local_path

    def _pull_from_minio(self, key: str, dest: str) -> None:
        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")
        alias = f"wasm-dl-{int(time.time() * 1e9)}"
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
                [mc, "cp", "--quiet", f"{alias}/{key}", dest],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)


def _download_file(url: str, dest: str) -> None:
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        with open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
