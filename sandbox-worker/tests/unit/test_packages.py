"""Unit tests for sandbox_platform.packages.store.PackageStore."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adapters.storage.local import PackageStore


@pytest.fixture
def store(tmp_path) -> PackageStore:
    """PackageStore backed by a temp local dir (no MinIO needed)."""
    return PackageStore(local_dir=str(tmp_path))


# ── install (sim / local-dir mode) ────────────────────────────────────────────


class TestInstallLocalDir:
    def test_returns_dict_with_name_and_version(self, store):
        result = store.install("numpy", version="1.26.0")
        assert result["name"] == "numpy"
        assert result["version"] == "1.26.0"

    def test_returns_status_installed(self, store):
        result = store.install("pandas", version="2.0.0")
        assert result["status"] == "installed"

    def test_creates_meta_json(self, store, tmp_path):
        store.install("scipy", version="1.12.0")
        meta_path = tmp_path / "scipy" / "1.12.0" / "meta.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["name"] == "scipy"
        assert data["version"] == "1.12.0"

    def test_version_defaults_to_latest(self, store, tmp_path):
        result = store.install("requests")
        assert result["version"] == "latest"
        meta_path = tmp_path / "requests" / "latest" / "meta.json"
        assert meta_path.exists()

    def test_idempotent_returns_cached_on_second_call(self, store):
        store.install("numpy", version="1.26.0")
        result2 = store.install("numpy", version="1.26.0")
        assert result2["status"] == "cached"

    def test_key_in_result(self, store):
        result = store.install("torch", version="2.2.0")
        assert "key" in result
        assert "torch" in result["key"]
        assert "2.2.0" in result["key"]


# ── list_packages ──────────────────────────────────────────────────────────────


class TestListPackages:
    def test_empty_when_nothing_installed(self, store):
        assert store.list_packages() == []

    def test_lists_installed_packages(self, store):
        store.install("numpy", version="1.26.0")
        store.install("pandas", version="2.0.0")
        pkgs = store.list_packages()
        names = {p["name"] for p in pkgs}
        assert names == {"numpy", "pandas"}

    def test_list_includes_version(self, store):
        store.install("scipy", version="1.12.0")
        pkgs = store.list_packages()
        assert pkgs[0]["version"] == "1.12.0"

    def test_list_includes_key(self, store):
        store.install("numpy", version="1.0.0")
        pkgs = store.list_packages()
        assert "key" in pkgs[0]

    def test_multiple_versions_of_same_package(self, store):
        store.install("numpy", version="1.25.0")
        store.install("numpy", version="1.26.0")
        pkgs = store.list_packages()
        versions = {p["version"] for p in pkgs if p["name"] == "numpy"}
        assert versions == {"1.25.0", "1.26.0"}


# ── delete ────────────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_removes_package(self, store, tmp_path):
        store.install("numpy", version="1.26.0")
        store.delete("numpy", version="1.26.0")
        meta_path = tmp_path / "numpy" / "1.26.0" / "meta.json"
        assert not meta_path.exists()

    def test_delete_not_in_list_after_removal(self, store):
        store.install("numpy", version="1.26.0")
        store.delete("numpy", version="1.26.0")
        pkgs = store.list_packages()
        assert not any(p["name"] == "numpy" for p in pkgs)

    def test_delete_nonexistent_does_not_raise(self, store):
        store.delete("nonexistent-pkg", version="9.9.9")  # should not raise

    def test_delete_only_specified_version(self, store):
        store.install("numpy", version="1.25.0")
        store.install("numpy", version="1.26.0")
        store.delete("numpy", version="1.25.0")
        pkgs = store.list_packages()
        remaining = [p for p in pkgs if p["name"] == "numpy"]
        assert len(remaining) == 1
        assert remaining[0]["version"] == "1.26.0"


# ── pip subprocess (real mode) ────────────────────────────────────────────────


class TestMinIOPaths:
    """Cover _list_minio, _delete_minio (stub warnings), and _store_wheel error."""

    def test_list_packages_no_local_dir_returns_empty(self):
        store = PackageStore(local_dir="")
        assert store.list_packages() == []

    def test_delete_no_local_dir_does_not_raise(self):
        store = PackageStore(local_dir="")
        store.delete("numpy", version="1.26.0")  # calls _delete_minio — just logs

    def test_store_wheel_raises_when_mc_not_found(self, tmp_path):
        store = PackageStore(local_dir="")
        fake_wheel = tmp_path / "pkg-1.0-py3-none-any.whl"
        fake_wheel.write_bytes(b"PK")
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="mc not found"):
                store._store_wheel("pkg", "1.0", fake_wheel)

    def test_store_wheel_calls_mc_alias_and_cp(self, tmp_path):
        store = PackageStore(local_dir="")
        fake_wheel = tmp_path / "pkg-1.0-py3-none-any.whl"
        fake_wheel.write_bytes(b"PK")
        mc_path = "/usr/bin/mc"
        with (
            patch("shutil.which", return_value=mc_path),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            result = store._store_wheel("pkg", "1.0", fake_wheel)
        assert result == "pkg/1.0/wheel.whl"
        # alias set, cp, alias remove = 3 calls
        assert mock_run.call_count == 3
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert any("alias" in cmd and "set" in cmd for cmd in cmds)
        assert any("cp" in cmd for cmd in cmds)
        assert any("alias" in cmd and "remove" in cmd for cmd in cmds)


class TestListLocalCorrupt:
    def test_corrupt_meta_json_is_silently_skipped(self, tmp_path):
        store = PackageStore(local_dir=str(tmp_path))
        # Install one valid package
        store.install("numpy", version="1.26.0")
        # Corrupt a second meta.json
        bad_dir = tmp_path / "bad" / "0.1"
        bad_dir.mkdir(parents=True)
        (bad_dir / "meta.json").write_text("not json{{{")
        # list_packages should return only the valid one
        pkgs = store.list_packages()
        assert len(pkgs) == 1
        assert pkgs[0]["name"] == "numpy"


class TestPipSubprocess:
    """PackageStore without local_dir uses pip; subprocess is mocked."""

    def _make_wheel(self, tmp_path, name, version):
        """Create a fake wheel file that pip would download."""
        wheel = tmp_path / f"{name}-{version}-py3-none-any.whl"
        wheel.write_bytes(b"PK\x03\x04")  # minimal ZIP magic bytes
        return wheel

    def test_pip_called_with_package_spec(self, tmp_path):
        store = PackageStore(local_dir="")  # real mode — would use pip + MinIO

        def fake_run(cmd, *args, **kwargs):
            # Simulate pip creating a wheel in the dest dir
            dest = None
            for i, arg in enumerate(cmd):
                if arg == "--dest" and i + 1 < len(cmd):
                    dest = cmd[i + 1]
            if dest:
                Path(dest).mkdir(parents=True, exist_ok=True)
                (Path(dest) / "numpy-1.26.0-py3-none-any.whl").write_bytes(b"PK")
            return MagicMock(returncode=0)

        with (
            patch("subprocess.run", side_effect=fake_run) as mock_run,
            patch.object(store, "_store_wheel", return_value="numpy/1.26.0/wheel.whl"),
        ):
            store.install("numpy", version="1.26.0")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        # cmd is [sys.executable, "-m", "pip", "download", ...]
        assert "pip" in cmd
        assert "download" in cmd
        assert "numpy==1.26.0" in cmd

    def test_proxy_url_passed_to_pip(self, tmp_path):
        store = PackageStore(local_dir="")

        def fake_run(cmd, *args, **kwargs):
            dest = None
            for i, arg in enumerate(cmd):
                if arg == "--dest" and i + 1 < len(cmd):
                    dest = cmd[i + 1]
            if dest:
                Path(dest).mkdir(parents=True, exist_ok=True)
                (Path(dest) / "numpy-1.26.0-py3-none-any.whl").write_bytes(b"PK")
            return MagicMock(returncode=0)

        with (
            patch("subprocess.run", side_effect=fake_run) as mock_run,
            patch.object(store, "_store_wheel", return_value="numpy/1.26.0/wheel.whl"),
        ):
            store.install("numpy", version="1.26.0", proxy_url="http://proxy:8080")

        cmd = mock_run.call_args[0][0]
        assert "--index-url" in cmd
        proxy_idx = cmd.index("--index-url")
        assert cmd[proxy_idx + 1] == "http://proxy:8080"

    def test_no_wheel_produced_raises(self, tmp_path):
        store = PackageStore(local_dir="")

        def fake_run(cmd, *args, **kwargs):
            dest = None
            for i, arg in enumerate(cmd):
                if arg == "--dest" and i + 1 < len(cmd):
                    dest = cmd[i + 1]
            if dest:
                Path(dest).mkdir(parents=True, exist_ok=True)
                # intentionally do NOT create a .whl file
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="no wheel"):
                store.install("numpy", version="1.26.0")

    def test_extra_dependencies_included_in_pip_call(self, tmp_path):
        store = PackageStore(local_dir="")

        def fake_run(cmd, *args, **kwargs):
            dest = None
            for i, arg in enumerate(cmd):
                if arg == "--dest" and i + 1 < len(cmd):
                    dest = cmd[i + 1]
            if dest:
                Path(dest).mkdir(parents=True, exist_ok=True)
                (Path(dest) / "scipy-1.12.0-py3-none-any.whl").write_bytes(b"PK")
            return MagicMock(returncode=0)

        with (
            patch("subprocess.run", side_effect=fake_run) as mock_run,
            patch.object(store, "_store_wheel", return_value="scipy/1.12.0/wheel.whl"),
        ):
            store.install("scipy", version="1.12.0", extra_dependencies=["numpy>=1.25"])

        cmd = mock_run.call_args[0][0]
        assert "numpy>=1.25" in cmd
