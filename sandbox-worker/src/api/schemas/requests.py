"""Request/Response schemas untuk API layer."""
from __future__ import annotations

from pydantic import BaseModel


class PackageInstallRequest(BaseModel):
    session_id: str = ""
    package_name: str
    version: str = ""
    proxy_url: str = ""
    timeout_seconds: int = 60
    extra_dependencies: list[str] = []
