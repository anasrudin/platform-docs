"""WorkspaceService — create, get, list files, and delete workspaces."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import structlog

from adapters.storage.base import BlobStore
from adapters.tracing import get_tracer
from models.workspace import MountConfig, MountDriver, Workspace, WorkspaceFile

log = structlog.get_logger()


class WorkspaceService:
    def __init__(
        self,
        storage: BlobStore,
        mounter,              # WorkspaceMounter
        driver: str = "sync",
        max_size_mb: int = 1024,
        bucket_prefix: str = "workspaces",
    ) -> None:
        self._storage = storage
        self._mounter = mounter
        self._driver = MountDriver(driver) if driver in MountDriver._value2member_map_ else MountDriver.SYNC
        self._max_size_mb = max_size_mb
        self._prefix = bucket_prefix
        # In-memory registry (later: DB)
        self._workspaces: dict[str, Workspace] = {}

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def create(self, name: str, tenant_id: str = "default") -> dict:
        tracer = get_tracer()
        with tracer.start_span("service.workspace.create", {"name": name, "tenant": tenant_id}):
            ws = Workspace(
                id=f"ws-{uuid.uuid4().hex[:8]}",
                name=name,
                tenant_id=tenant_id,
            )
            self._workspaces[ws.id] = ws
            log.info("workspace created", workspace_id=ws.id, name=name)
            return {"workspace_id": ws.id, "created_at": ws.created_at.isoformat()}

    def get(self, workspace_id: str) -> dict:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise KeyError(f"workspace not found: {workspace_id}")
        files = self._list_files(workspace_id)
        size = sum(f.size for f in files)
        return {
            "workspace_id": ws.id,
            "name": ws.name,
            "tenant_id": ws.tenant_id,
            "size_bytes": size,
            "files": [{"path": f.path, "size": f.size, "modified": f.modified.isoformat()} for f in files],
        }

    def delete(self, workspace_id: str) -> None:
        tracer = get_tracer()
        with tracer.start_span("service.workspace.delete", {"workspace_id": workspace_id}):
            ws = self._workspaces.pop(workspace_id, None)
            if ws is None:
                raise KeyError(f"workspace not found: {workspace_id}")
            # Delete all blobs
            files = self._list_files(workspace_id)
            self._mounter.delete(workspace_id, [f.path for f in files])
            # Delete manifest
            try:
                self._storage.delete(f"{self._prefix}/{workspace_id}/_manifest.json")
            except Exception:
                pass
            log.info("workspace deleted", workspace_id=workspace_id)

    def list_files(self, workspace_id: str) -> list[dict]:
        self._require(workspace_id)
        return [
            {"path": f.path, "size": f.size, "modified": f.modified.isoformat()}
            for f in self._list_files(workspace_id)
        ]

    # ── Mount helpers ──────────────────────────────────────────────────────────

    def mount_config(self, workspace_id: str) -> MountConfig:
        self._require(workspace_id)
        return MountConfig(workspace_id=workspace_id, driver=self._driver)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _require(self, workspace_id: str) -> Workspace:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise KeyError(f"workspace not found: {workspace_id}")
        return ws

    def _list_files(self, workspace_id: str) -> list[WorkspaceFile]:
        manifest_key = f"{self._prefix}/{workspace_id}/_manifest.json"
        try:
            data = self._storage.download(manifest_key)
            names = json.loads(data.decode())
        except Exception:
            return []
        result = []
        for name in names:
            key = f"{self._prefix}/{workspace_id}/{name}"
            try:
                blob = self._storage.download(key)
                result.append(WorkspaceFile(
                    path=name,
                    size=len(blob),
                    modified=datetime.utcnow(),
                ))
            except Exception:
                pass
        return result
