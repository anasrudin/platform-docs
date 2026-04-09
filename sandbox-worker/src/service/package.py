"""PackageService — install, list, and delete sandbox packages."""
from __future__ import annotations

import structlog

from adapters.storage.local import PackageStore

log = structlog.get_logger()


class PackageService:
    def __init__(self, store: PackageStore) -> None:
        self._store = store

    def install(
        self,
        name: str,
        version: str = "",
        proxy_url: str = "",
        timeout_seconds: int = 60,
        extra_dependencies: list[str] | None = None,
    ) -> dict:
        return self._store.install(
            name=name,
            version=version,
            proxy_url=proxy_url,
            timeout_seconds=timeout_seconds,
            extra_dependencies=extra_dependencies or [],
        )

    def list_packages(self) -> list[dict]:
        return self._store.list_packages()

    def delete(self, name: str, version: str = "") -> None:
        self._store.delete(name, version=version)
