"""Unit tests for sandbox_platform.artifacts.store."""
import io
import os
import tempfile
from pathlib import Path

import pytest

from sandbox_platform.artifacts.store import (
    Config,
    Store,
    ensure_local_dir,
    local_path,
    mc_available,
)


class TestConfig:
    def test_from_env_defaults(self, monkeypatch):
        for key in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
                    "MINIO_ARTIFACTS_BUCKET", "ARTIFACTS_LOCAL_DIR"):
            monkeypatch.delenv(key, raising=False)
        cfg = Config.from_env()
        assert cfg.endpoint == "http://localhost:9000"
        assert cfg.access_key == "minioadmin"
        assert cfg.bucket == "platform-artifacts"
        assert cfg.local_dir == ""

    def test_from_env_custom(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
        monkeypatch.setenv("MINIO_ARTIFACTS_BUCKET", "my-bucket")
        cfg = Config.from_env()
        assert cfg.endpoint == "http://minio:9000"
        assert cfg.bucket == "my-bucket"


class TestLocalStore:
    def test_upload_and_download(self, tmp_path):
        cfg = Config(local_dir=str(tmp_path))
        store = Store(cfg)

        content = b"hello world"
        store.upload("art-1", "test.txt", io.BytesIO(content))

        buf = io.BytesIO()
        store.download("art-1/test.txt", buf)
        assert buf.getvalue() == content

    def test_upload_creates_subdirs(self, tmp_path):
        cfg = Config(local_dir=str(tmp_path))
        store = Store(cfg)

        store.upload("nested/id", "file.bin", io.BytesIO(b"data"))
        assert (tmp_path / "nested" / "id" / "file.bin").exists()

    def test_url_local_returns_path(self, tmp_path):
        cfg = Config(local_dir=str(tmp_path))
        store = Store(cfg)
        assert store.url("abc/file.txt") == "/artifacts/abc/file.txt"

    def test_url_minio_returns_full_url(self):
        cfg = Config(endpoint="http://minio:9000", bucket="my-bucket")
        store = Store(cfg)
        assert store.url("abc/file.txt") == "http://minio:9000/my-bucket/abc/file.txt"

    def test_download_missing_file_raises(self, tmp_path):
        cfg = Config(local_dir=str(tmp_path))
        store = Store(cfg)
        with pytest.raises(FileNotFoundError):
            store.download("no/such/file.txt", io.BytesIO())

    def test_ensure_bucket_local_creates_dir(self, tmp_path):
        target = tmp_path / "new_bucket"
        cfg = Config(local_dir=str(target))
        store = Store(cfg)
        store.ensure_bucket()
        assert target.exists()


class TestHelpers:
    def test_local_path_joins_correctly(self, tmp_path):
        result = local_path(str(tmp_path), "id/file.txt")
        assert result == str(tmp_path / "id" / "file.txt")

    def test_ensure_local_dir_creates(self, tmp_path):
        target = tmp_path / "nested" / "dir"
        ensure_local_dir(str(target))
        assert target.exists()

    def test_ensure_local_dir_idempotent(self, tmp_path):
        """Mirrors TestEnsureLocalDir_Idempotent from store_test.go."""
        target = tmp_path / "sub"
        ensure_local_dir(str(target))
        ensure_local_dir(str(target))  # second call must not raise
        assert target.exists()

    def test_mc_available_returns_bool(self):
        result = mc_available()
        assert isinstance(result, bool)

    def test_url_contains_key(self):
        """Mirrors TestStore_URL_NoTrailingSlash from store_test.go."""
        cfg = Config(endpoint="http://localhost:9000/", bucket="my-bucket")
        store = Store(cfg)
        url = store.url("id/file.wasm")
        assert "id/file.wasm" in url


class TestNoMCErrors:
    """Mirrors the 'without mc' tests in store_test.go."""

    def _no_mc_store(self) -> Store:
        return Store(Config(
            endpoint="http://127.0.0.1:1",
            access_key="test",
            secret_key="test",
            bucket="test-bucket",
        ))

    def test_upload_fails_gracefully_without_mc(self):
        """Mirrors TestUpload_FailsGracefullyWithoutMC."""
        if mc_available():
            pytest.skip("mc is installed — test is for environments without mc")
        import io
        store = self._no_mc_store()
        with pytest.raises(Exception) as exc_info:
            store.upload("test-id", "test.txt", io.BytesIO(b"hello"))
        assert str(exc_info.value) != ""  # error must have a message, no silent failure

    def test_download_fails_gracefully_without_mc(self):
        """Mirrors TestDownload_FailsGracefullyWithoutMC."""
        if mc_available():
            pytest.skip("mc is installed — test is for environments without mc")
        import io
        store = self._no_mc_store()
        with pytest.raises(Exception):
            store.download("nonexistent/file.txt", io.BytesIO())

    def test_ensure_bucket_fails_without_mc(self):
        """Mirrors TestEnsureBucket_FailsWithoutMC."""
        if mc_available():
            pytest.skip("mc is installed — test is for environments without mc")
        store = self._no_mc_store()
        with pytest.raises(Exception) as exc_info:
            store.ensure_bucket()
        assert "mc" in str(exc_info.value).lower()
