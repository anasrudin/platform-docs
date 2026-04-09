"""Package wheel cache backed by MinIO (platform-packages bucket) with local
filesystem fallback for development.

Mode selection (mirrors artifact store pattern):
  - ``PACKAGES_LOCAL_DIR`` set   → local filesystem, no pip/MinIO needed
  - otherwise                    → real mode: pip download → MinIO upload

Bucket layout::

    platform-packages/
      {name}/{version}/meta.json    – package metadata
      {name}/{version}/wheel.whl    – the downloaded wheel

Environment variables:
  MINIO_ENDPOINT        (default: http://localhost:9000)
  MINIO_ACCESS_KEY      (default: minioadmin)
  MINIO_SECRET_KEY      (default: minioadmin)
  PACKAGES_LOCAL_DIR    – when set, use local FS instead of MinIO
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import structlog

log = structlog.get_logger()


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


class PackageStore:
    """Cache pip wheels in MinIO (or a local directory in dev mode)."""

    BUCKET = "platform-packages"

    def __init__(
        self,
        local_dir: str = "",
        endpoint: str = "",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "",
    ) -> None:
        self._local_dir = local_dir or _env_or("PACKAGES_LOCAL_DIR", "")
        self._endpoint = endpoint or _env_or("MINIO_ENDPOINT", "http://localhost:9000")
        self._access_key = access_key or _env_or("MINIO_ACCESS_KEY", "minioadmin")
        self._secret_key = secret_key or _env_or("MINIO_SECRET_KEY", "minioadmin")
        self._bucket = bucket or self.BUCKET

    # ── Public API ─────────────────────────────────────────────────────────────

    def install(
        self,
        name: str,
        version: str = "",
        proxy_url: str = "",
        timeout_seconds: int = 60,
        extra_dependencies: list[str] | None = None,
    ) -> dict:
        """Install a package and cache its wheel. Returns metadata dict.

        Status is ``"cached"`` if the wheel is already present, ``"installed"``
        if it was freshly downloaded.
        """
        resolved_version = version or "latest"
        key = self._key(name, resolved_version)

        if self._is_cached(name, resolved_version):
            log.info("packages: cache hit", name=name, version=resolved_version)
            return {
                "name": name,
                "version": resolved_version,
                "key": key,
                "status": "cached",
            }

        if self._local_dir:
            return self._sim_install(name, resolved_version, key)

        return self._pip_install(
            name,
            resolved_version,
            key,
            proxy_url=proxy_url,
            timeout_seconds=timeout_seconds,
            extra_deps=extra_dependencies or [],
        )

    def list_packages(self) -> list[dict]:
        """Return a list of all cached packages."""
        if self._local_dir:
            return self._list_local()
        return self._list_minio()

    def delete(self, name: str, version: str = "") -> None:
        """Remove a specific package version from the cache."""
        resolved_version = version or "latest"
        if self._local_dir:
            self._delete_local(name, resolved_version)
        else:
            self._delete_minio(name, resolved_version)

    # ── Local dir (sim) ────────────────────────────────────────────────────────

    def _sim_install(self, name: str, version: str, key: str) -> dict:
        pkg_dir = Path(self._local_dir) / name / version
        pkg_dir.mkdir(parents=True, exist_ok=True)
        meta = {"name": name, "version": version, "key": key, "status": "installed"}
        (pkg_dir / "meta.json").write_text(json.dumps(meta))
        # Stub wheel placeholder
        (pkg_dir / "wheel.whl").write_bytes(b"")
        log.info("packages: sim install", name=name, version=version)
        return meta

    def _is_cached(self, name: str, version: str) -> bool:
        if self._local_dir:
            return (Path(self._local_dir) / name / version / "meta.json").exists()
        return False  # MinIO cache check not implemented in unit-test scope

    def _list_local(self) -> list[dict]:
        base = Path(self._local_dir)
        result: list[dict] = []
        for meta_file in base.glob("*/*/meta.json"):
            try:
                data = json.loads(meta_file.read_text())
                result.append(data)
            except Exception:
                pass
        return result

    def _delete_local(self, name: str, version: str) -> None:
        pkg_dir = Path(self._local_dir) / name / version
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)

    # ── Real mode (pip + MinIO) ────────────────────────────────────────────────

    def _pip_install(
        self,
        name: str,
        version: str,
        key: str,
        proxy_url: str,
        timeout_seconds: int,
        extra_deps: list[str],
    ) -> dict:
        spec = f"{name}=={version}" if version != "latest" else name
        with tempfile.TemporaryDirectory(prefix="pkg-") as tmp:
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--no-deps",
                "--dest",
                tmp,
                spec,
            ]
            if proxy_url:
                cmd += ["--index-url", proxy_url]
            for dep in extra_deps:
                cmd.append(dep)

            subprocess.run(cmd, check=True, timeout=timeout_seconds)

            wheels = list(Path(tmp).glob("*.whl"))
            if not wheels:
                raise RuntimeError(f"pip download produced no wheel for {spec}")

            wheel_path = wheels[0]
            stored_key = self._store_wheel(name, version, wheel_path)

        meta = {
            "name": name,
            "version": version,
            "key": stored_key,
            "status": "installed",
        }
        log.info("packages: installed", name=name, version=version, key=stored_key)
        return meta

    def _store_wheel(self, name: str, version: str, wheel_path: Path) -> str:
        """Upload wheel to MinIO; returns the object key."""
        key = self._key(name, version)
        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found; cannot store wheel in MinIO")
        alias = f"pkg-{os.getpid()}"
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
                [
                    mc,
                    "cp",
                    "--quiet",
                    str(wheel_path),
                    f"{alias}/{self._bucket}/{key}/wheel.whl",
                ],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)
        return f"{key}/wheel.whl"

    def _list_minio(self) -> list[dict]:
        log.warning("packages: MinIO list not implemented in sim scope")
        return []

    def _delete_minio(self, name: str, version: str) -> None:
        log.warning(
            "packages: MinIO delete not implemented in sim scope",
            name=name,
            version=version,
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _key(name: str, version: str) -> str:
        return f"{name}/{version}"
