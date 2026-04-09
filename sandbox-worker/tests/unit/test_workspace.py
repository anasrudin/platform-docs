"""Tests for Workspace Persistence — models, orchestrator, service, api routes."""
from __future__ import annotations

import json
import pytest

from adapters.tracing import init_tracer, reset_tracer
from models.workspace import MountDriver, MountConfig, Workspace


@pytest.fixture(autouse=True)
def tracer():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


# ── MemStorage helper ──────────────────────────────────────────────────────────

class MemStorage:
    def __init__(self):
        self._data: dict[str, bytes] = {}

    def upload(self, key, data, **kw):
        self._data[key] = data
        return key

    def download(self, key):
        if key not in self._data:
            raise FileNotFoundError(key)
        return self._data[key]

    def delete(self, key):
        self._data.pop(key, None)

    def exists(self, key):
        return key in self._data


# ── WorkspaceMounter ───────────────────────────────────────────────────────────

class TestWorkspaceMounter:
    def _make(self):
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        return WorkspaceMounter(storage), storage

    def test_mount_empty_workspace_creates_dir(self, tmp_path):
        mounter, _ = self._make()
        config = MountConfig(workspace_id="ws-1")
        result = mounter.mount(config, str(tmp_path / "ws"))
        assert result == str(tmp_path / "ws")
        assert (tmp_path / "ws").exists()

    def test_unmount_uploads_files(self, tmp_path):
        mounter, storage = self._make()
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        (ws_dir / "hello.txt").write_bytes(b"hello")
        config = MountConfig(workspace_id="ws-1")
        total = mounter.unmount(config, str(ws_dir))
        assert total > 0
        assert any("hello.txt" in k for k in storage._data)

    def test_mount_restores_uploaded_files(self, tmp_path):
        mounter, storage = self._make()
        # First upload a file
        ws_dir = tmp_path / "ws-src"
        ws_dir.mkdir()
        (ws_dir / "data.txt").write_bytes(b"workspace data")
        config = MountConfig(workspace_id="ws-2")
        mounter.unmount(config, str(ws_dir))

        # Now mount to a fresh dir
        restore_dir = tmp_path / "ws-dst"
        mounter.mount(config, str(restore_dir))
        assert (restore_dir / "data.txt").read_bytes() == b"workspace data"

    def test_delete_removes_blobs(self, tmp_path):
        mounter, storage = self._make()
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        (ws_dir / "file.py").write_bytes(b"code")
        config = MountConfig(workspace_id="ws-del")
        mounter.unmount(config, str(ws_dir))
        assert len(storage._data) > 0
        mounter.delete("ws-del", ["file.py"])
        assert not any("file.py" in k for k in storage._data)


# ── WorkspaceService ───────────────────────────────────────────────────────────

class TestWorkspaceService:
    def _make(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        mounter = WorkspaceMounter(storage)
        svc = WorkspaceService(storage=storage, mounter=mounter)
        return svc, storage

    def test_create_returns_workspace_id(self):
        svc, _ = self._make()
        result = svc.create("my-project")
        assert result["workspace_id"].startswith("ws-")
        assert "created_at" in result

    def test_get_after_create(self):
        svc, _ = self._make()
        ws_id = svc.create("proj")["workspace_id"]
        info = svc.get(ws_id)
        assert info["workspace_id"] == ws_id
        assert info["name"] == "proj"

    def test_get_unknown_raises_key_error(self):
        svc, _ = self._make()
        with pytest.raises(KeyError):
            svc.get("ws-nonexistent")

    def test_delete_removes_workspace(self):
        svc, _ = self._make()
        ws_id = svc.create("tmp")["workspace_id"]
        svc.delete(ws_id)
        with pytest.raises(KeyError):
            svc.get(ws_id)

    def test_delete_unknown_raises_key_error(self):
        svc, _ = self._make()
        with pytest.raises(KeyError):
            svc.delete("ws-gone")

    def test_list_files_empty_initially(self):
        svc, _ = self._make()
        ws_id = svc.create("empty")["workspace_id"]
        files = svc.list_files(ws_id)
        assert files == []

    def test_list_files_after_upload(self, tmp_path):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        mounter = WorkspaceMounter(storage)
        svc = WorkspaceService(storage=storage, mounter=mounter)
        ws_id = svc.create("with-files")["workspace_id"]

        # Simulate a file being uploaded via mounter
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        (ws_dir / "analysis.py").write_bytes(b"# code")
        config = svc.mount_config(ws_id)
        mounter.unmount(config, str(ws_dir))

        files = svc.list_files(ws_id)
        assert any(f["path"] == "analysis.py" for f in files)

    def test_tenant_isolation(self):
        svc, _ = self._make()
        ws_a = svc.create("proj-a", tenant_id="tenant-a")["workspace_id"]
        ws_b = svc.create("proj-b", tenant_id="tenant-b")["workspace_id"]
        info_a = svc.get(ws_a)
        info_b = svc.get(ws_b)
        assert info_a["tenant_id"] == "tenant-a"
        assert info_b["tenant_id"] == "tenant-b"

    def test_mount_config_uses_configured_driver(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        mounter = WorkspaceMounter(storage)
        svc = WorkspaceService(storage=storage, mounter=mounter, driver="sync")
        ws_id = svc.create("proj")["workspace_id"]
        cfg = svc.mount_config(ws_id)
        assert cfg.driver == MountDriver.SYNC
        assert cfg.workspace_id == ws_id


# ── Workspace API routes ───────────────────────────────────────────────────────

class TestWorkspaceRoutes:
    def _make_app(self, svc=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.workspace import register
        app = FastAPI()
        app.include_router(register({"workspace_svc": svc}))
        return TestClient(app)

    def test_create_no_svc_returns_503(self):
        client = self._make_app()
        resp = client.post("/workspaces", json={"name": "proj"})
        assert resp.status_code == 503

    def test_create_returns_201(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        svc = WorkspaceService(storage=storage, mounter=WorkspaceMounter(storage))
        client = self._make_app(svc)
        resp = client.post("/workspaces", json={"name": "my-ws"})
        assert resp.status_code == 201
        assert resp.json()["workspace_id"].startswith("ws-")

    def test_get_returns_workspace(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        svc = WorkspaceService(storage=storage, mounter=WorkspaceMounter(storage))
        ws_id = svc.create("test")["workspace_id"]
        client = self._make_app(svc)
        resp = client.get(f"/workspaces/{ws_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test"

    def test_get_unknown_returns_404(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        svc = WorkspaceService(storage=storage, mounter=WorkspaceMounter(storage))
        client = self._make_app(svc)
        resp = client.get("/workspaces/ws-unknown")
        assert resp.status_code == 404

    def test_delete_returns_204(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        svc = WorkspaceService(storage=storage, mounter=WorkspaceMounter(storage))
        ws_id = svc.create("to-delete")["workspace_id"]
        client = self._make_app(svc)
        resp = client.delete(f"/workspaces/{ws_id}")
        assert resp.status_code == 204

    def test_list_files_returns_empty_array(self):
        from service.workspace import WorkspaceService
        from orchestrator.workspace import WorkspaceMounter
        storage = MemStorage()
        svc = WorkspaceService(storage=storage, mounter=WorkspaceMounter(storage))
        ws_id = svc.create("empty-ws")["workspace_id"]
        client = self._make_app(svc)
        resp = client.get(f"/workspaces/{ws_id}/files")
        assert resp.status_code == 200
        assert resp.json()["files"] == []
