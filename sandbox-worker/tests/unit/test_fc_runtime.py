"""Unit tests for sandbox_platform.runtime.firecracker.runtime."""

import json
from datetime import datetime, timezone
from unittest.mock import patch


from runtime.firecracker import Config, Runtime, detect_mode
from models.job import Job, JobStatus
from models.session import Tier


def _make_job(tool: str, input_data: dict = None) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id="j-fc-1",
        session_id="s1",
        tool=tool,
        tier=Tier.MICROVM,
        input=input_data or {},
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


class TestDetectMode:
    def test_env_sim(self, monkeypatch):
        monkeypatch.setenv("FC_MODE", "sim")
        assert detect_mode() == "sim"

    def test_env_real(self, monkeypatch):
        monkeypatch.setenv("FC_MODE", "real")
        assert detect_mode() == "real"

    def test_auto_detect_no_kvm(self, monkeypatch):
        monkeypatch.delenv("FC_MODE", raising=False)
        with patch("os.path.exists", return_value=False):
            assert detect_mode() == "sim"

    def test_auto_detect_kvm_present(self, monkeypatch):
        monkeypatch.delenv("FC_MODE", raising=False)
        with patch("os.path.exists", return_value=True):
            assert detect_mode() == "real"


class TestConfig:
    """Mirrors TestConfigFromEnv_Defaults / TestConfigFromEnv_Overrides in runtime_test.go."""

    def test_defaults(self, monkeypatch):
        for key in (
            "FC_BIN",
            "SNAPSHOT_NAME",
            "SNAPSHOT_CACHE_DIR",
            "MINIO_ENDPOINT",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
            "MINIO_BUCKET",
            "FC_POOL_SIZE",
            "FC_DEV_MODE",
        ):
            monkeypatch.delenv(key, raising=False)
        cfg = Config()
        assert cfg.firecracker_bin == "/usr/bin/firecracker"
        assert cfg.snapshot_name == "python-v1"
        assert cfg.snapshot_cache_dir == "/var/sandbox/cache"
        assert cfg.minio_endpoint == "http://localhost:9000"
        assert cfg.minio_bucket == "platform-snapshots"
        assert cfg.pool_size == 2
        assert cfg.dev_mode is False

    def test_overrides(self, monkeypatch):
        monkeypatch.setenv("FC_BIN", "/opt/fc/firecracker")
        monkeypatch.setenv("SNAPSHOT_NAME", "go-v1")
        monkeypatch.setenv("FC_POOL_SIZE", "4")
        monkeypatch.setenv("FC_DEV_MODE", "true")
        cfg = Config()
        assert cfg.firecracker_bin == "/opt/fc/firecracker"
        assert cfg.snapshot_name == "go-v1"
        assert cfg.pool_size == 4
        assert cfg.dev_mode is True

    def test_pool_size_invalid_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("FC_POOL_SIZE", "notanumber")
        cfg = Config()
        assert cfg.pool_size == 2


class TestFirecrackerRuntimeSim:
    def _sim_runtime(self, monkeypatch) -> Runtime:
        monkeypatch.setenv("FC_MODE", "sim")
        return Runtime()

    def test_name(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        assert rt.name() == "firecracker-sim"

    def test_tier(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        assert rt.tier() is Tier.MICROVM

    def test_health_sim_no_error(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        rt.health()  # should not raise

    def test_simulate_python_run(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("python_run", {"code": "print('hi')"})
        result = rt.execute(job)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["runtime"] == "firecracker-sim"
        assert "sim_note" in data
        output = data["output"]
        assert "sim" in output["stdout"]

    def test_simulate_bash_run(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("bash_run", {"command": "ls"})
        result = rt.execute(job)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "ls" in data["output"]["stdout"]

    def test_simulate_unknown_tool(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("some_tool", {"x": 1})
        result = rt.execute(job)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["tool"] == "some_tool"

    def test_simulate_result_has_metadata(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("python_run", {})
        result = rt.execute(job)
        data = json.loads(result.stdout)
        assert "metadata" in data
        assert "kernel" in data["metadata"]
        assert "mem_mib" in data["metadata"]

    def test_simulate_vm_id_is_unique(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job1 = _make_job("echo", {})
        job2 = _make_job("echo", {})
        r1 = json.loads(rt.execute(job1).stdout)
        r2 = json.loads(rt.execute(job2).stdout)
        assert r1["vm_id"] != r2["vm_id"]
