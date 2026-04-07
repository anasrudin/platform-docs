"""Unit tests for sandbox_platform.runtime.wasm.runtime."""
import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sandbox_platform.runtime.wasm.runtime import Runtime, detect_mode
from sandbox_platform.types import Job, JobStatus, Tier


def _make_job(tool: str, input_data: dict = None) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id="j1", session_id="s1", tool=tool,
        tier=Tier.WASM, input=input_data or {},
        status=JobStatus.PENDING, created_at=now, updated_at=now,
    )


class TestDetectMode:
    def test_env_var_sim(self, monkeypatch):
        monkeypatch.setenv("WASM_MODE", "sim")
        assert detect_mode("wasmtime") == "sim"

    def test_env_var_real(self, monkeypatch):
        monkeypatch.setenv("WASM_MODE", "real")
        assert detect_mode("wasmtime") == "real"

    def test_auto_detect_no_wasmtime(self, monkeypatch):
        monkeypatch.delenv("WASM_MODE", raising=False)
        with patch("shutil.which", return_value=None):
            assert detect_mode("wasmtime") == "sim"

    def test_auto_detect_wasmtime_found(self, monkeypatch):
        monkeypatch.delenv("WASM_MODE", raising=False)
        with patch("shutil.which", return_value="/usr/local/bin/wasmtime"):
            assert detect_mode("wasmtime") == "real"


class TestWasmRuntime:
    def _sim_runtime(self, monkeypatch) -> Runtime:
        monkeypatch.setenv("WASM_MODE", "sim")
        return Runtime()

    def test_name_contains_mode(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        assert "wasm-sim" == rt.name()

    def test_tier_is_wasm(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        assert rt.tier() is Tier.WASM

    def test_health_sim_mode_no_error(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        rt.health()  # should not raise

    def test_echo_handler(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("echo", {"key": "value"})
        result = rt.execute(job)
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["key"] == "value"

    def test_hello_handler_default(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("hello", {})
        result = rt.execute(job)
        assert result.exit_code == 0
        assert "Hello, World!" in result.stdout

    def test_hello_handler_with_name(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("hello", {"name": "Alice"})
        result = rt.execute(job)
        assert "Hello, Alice!" in result.stdout

    def test_json_parse_valid(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("json_parse", {"data": '{"x": 42}'})
        result = rt.execute(job)
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["x"] == 42

    def test_json_parse_invalid_json(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("json_parse", {"data": "not json"})
        result = rt.execute(job)
        assert result.exit_code == 1
        assert "JSON" in result.stderr or "invalid" in result.stderr.lower()

    def test_json_parse_missing_field(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("json_parse", {})
        result = rt.execute(job)
        assert result.exit_code == 1

    def test_html_parse(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("html_parse", {"html": "<p>hello</p>"})
        result = rt.execute(job)
        assert result.exit_code == 0
        assert "bytes" in result.stdout

    def test_markdown_convert(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("markdown_convert", {"markdown": "# Title"})
        result = rt.execute(job)
        assert result.exit_code == 0
        assert "<html>" in result.stdout

    def test_unknown_tool_falls_back_to_echo(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        job = _make_job("completely_unknown_tool", {"foo": "bar"})
        result = rt.execute(job)
        # Falls back to echo handler
        assert result.exit_code == 0

    def test_custom_handler_registration(self, monkeypatch):
        rt = self._sim_runtime(monkeypatch)
        rt.register_handler("my_tool", lambda inp: (f"custom:{inp.get('v')}", None))
        job = _make_job("my_tool", {"v": "test"})
        result = rt.execute(job)
        assert result.stdout == "custom:test"
        assert result.exit_code == 0


class TestWasmRealExec:
    """Mirrors TestRealExec_FallsBackToSimOnMissingModule from runtime_test.go."""

    def test_real_exec_falls_back_to_sim_when_module_missing(self, monkeypatch, tmp_path):
        """realExec falls back to simExec when module download fails (unreachable MinIO)."""
        monkeypatch.setenv("WASM_MODE", "real")
        monkeypatch.setenv("WASM_CACHE_DIR", str(tmp_path))  # empty cache
        monkeypatch.setenv("MINIO_ENDPOINT", "http://127.0.0.1:1")  # unreachable
        rt = Runtime()
        job = _make_job("echo", {"x": "fallback-test"})
        result = rt.execute(job)
        # Should fall back to echo sim handler → exit 0
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["x"] == "fallback-test"
