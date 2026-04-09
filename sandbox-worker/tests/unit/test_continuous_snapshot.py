"""Tests for continuous snapshot: load/save/delete session snapshots."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from orchestrator.snapshot import SnapshotDownloader, SnapshotPaths


def _make_downloader(tmp_path, storage=None):
    if storage is None:
        storage = MagicMock()
        storage.exists.return_value = False
    return SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))


def _write_snapshot_blobs(directory: str) -> None:
    """Write fake vmstate.bin, memory.bin, meta.json to directory."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    Path(directory, "vmstate.bin").write_bytes(b"vmstate")
    Path(directory, "memory.bin").write_bytes(b"memory")
    Path(directory, "meta.json").write_text(json.dumps({
        "name": "test", "version": "1", "kernel": "vmlinux",
        "rootfs": "rootfs.ext4", "vcpus": 1, "mem_mib": 128,
    }))


class TestLoadSessionSnapshot:
    def test_returns_none_when_not_in_cache_or_storage(self, tmp_path):
        dl = _make_downloader(tmp_path)
        result = dl.load_session_snapshot("sess-123")
        assert result is None

    def test_returns_paths_from_local_cache(self, tmp_path):
        local_dir = tmp_path / "sessions" / "sess-abc"
        _write_snapshot_blobs(str(local_dir))

        dl = _make_downloader(tmp_path)
        result = dl.load_session_snapshot("sess-abc")

        assert result is not None
        assert result.state_file.endswith("vmstate.bin")
        assert result.mem_file.endswith("memory.bin")

    def test_downloads_from_storage_when_not_cached(self, tmp_path):
        storage = MagicMock()
        storage.exists.return_value = True
        storage.download.side_effect = lambda key: (
            b"vmstate" if "vmstate" in key else
            b"memory" if "memory" in key else
            json.dumps({"name": "s", "version": "1", "kernel": "k",
                        "rootfs": "r", "vcpus": 1, "mem_mib": 128}).encode()
        )

        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        result = dl.load_session_snapshot("sess-dl")

        assert result is not None
        assert storage.download.call_count == 3  # vmstate, memory, meta

    def test_returns_none_if_storage_missing_any_blob(self, tmp_path):
        storage = MagicMock()
        storage.exists.side_effect = lambda key: "vmstate" not in key  # vmstate missing

        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        result = dl.load_session_snapshot("sess-missing")
        assert result is None


class TestSaveSessionSnapshot:
    def test_uploads_all_blobs(self, tmp_path):
        local_dir = tmp_path / "src"
        _write_snapshot_blobs(str(local_dir))

        storage = MagicMock()
        storage.upload.return_value = "sessions/sess-save/vmstate.bin"

        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        dl.save_session_snapshot("sess-save", str(local_dir))

        assert storage.upload.call_count == 3
        uploaded_keys = [c.args[0] for c in storage.upload.call_args_list]
        assert "sessions/sess-save/vmstate.bin" in uploaded_keys
        assert "sessions/sess-save/memory.bin" in uploaded_keys
        assert "sessions/sess-save/meta.json" in uploaded_keys


class TestDeleteSessionSnapshot:
    def test_deletes_all_blobs_from_storage(self, tmp_path):
        storage = MagicMock()
        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        dl.delete_session_snapshot("sess-del")

        assert storage.delete.call_count == 3
        deleted_keys = [c.args[0] for c in storage.delete.call_args_list]
        assert "sessions/sess-del/vmstate.bin" in deleted_keys
        assert "sessions/sess-del/memory.bin" in deleted_keys
        assert "sessions/sess-del/meta.json" in deleted_keys

    def test_clears_local_cache(self, tmp_path):
        local_dir = tmp_path / "sessions" / "sess-clear"
        _write_snapshot_blobs(str(local_dir))
        assert local_dir.exists()

        storage = MagicMock()
        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        dl.delete_session_snapshot("sess-clear")

        assert not local_dir.exists()

    def test_delete_ignores_storage_errors(self, tmp_path):
        storage = MagicMock()
        storage.delete.side_effect = Exception("not found")
        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        # Should not raise
        dl.delete_session_snapshot("sess-err")


# ── SessionService snapshot_mode tests ───────────────────────────────────────

import pytest
from adapters.tracing import init_tracer, reset_tracer
from service.session import SessionService


@pytest.fixture(autouse=True)
def tracer_setup():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


class TestSessionServiceSnapshotMode:
    def test_default_is_clean(self):
        import asyncio
        svc = SessionService()
        result = asyncio.run(svc.create("wasm"))
        assert result["snapshot_mode"] == "clean"

    def test_continuous_mode_stored(self):
        import asyncio
        svc = SessionService()
        result = asyncio.run(svc.create("wasm", "continuous"))
        assert result["snapshot_mode"] == "continuous"

    def test_invalid_mode_falls_back_to_clean(self):
        import asyncio
        svc = SessionService()
        result = asyncio.run(svc.create("wasm", "invalid_mode"))
        assert result["snapshot_mode"] == "clean"
