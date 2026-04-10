"""Tests for ExecutionService — verifies the vm.execute() fix.

Bug fixed: execution.py previously called vm.run(job), which does not exist
on FirecrackerVM. The correct API is vm.execute(tool, input_data) returning
a GuestResponse. These tests verify the fixed call path.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adapters.tracing import init_tracer, reset_tracer
from runtime.firecracker import GuestResponse
from service.execution import ExecutionService


@pytest.fixture(autouse=True)
def tracer_setup():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


def _make_svc(exit_code: int = 0, stdout: str = "hello", stderr: str = "") -> tuple[ExecutionService, MagicMock]:
    """Return (svc, mock_vm) — mock_vm has .execute() returning GuestResponse."""
    mock_vm = MagicMock()
    mock_vm.execute.return_value = GuestResponse(
        exit_code=exit_code, stdout=stdout, stderr=stderr
    )
    mock_mgr = MagicMock()
    mock_mgr.acquire.return_value = mock_vm
    mock_mgr._cache_dir = "/tmp/test-cache"
    svc = ExecutionService(lifecycle_mgr=mock_mgr)
    return svc, mock_vm


class TestExecutionServiceVmCall:
    def test_calls_vm_execute_not_run(self):
        """vm.execute(tool, input) must be called — not the old vm.run(job)."""
        svc, mock_vm = _make_svc()
        svc.execute({"tool": "python_run", "input": {"code": "print(1)"}})
        mock_vm.execute.assert_called_once_with("python_run", {"code": "print(1)"})
        mock_vm.run.assert_not_called()  # old broken interface must NOT be called

    def test_passes_correct_tool_and_input(self):
        svc, mock_vm = _make_svc()
        svc.execute({"tool": "bash_run", "input": {"command": "ls -la"}})
        mock_vm.execute.assert_called_once_with("bash_run", {"command": "ls -la"})

    def test_returns_completed_on_exit_code_zero(self):
        svc, _ = _make_svc(exit_code=0, stdout="output here")
        result = svc.execute({"tool": "python_run", "input": {}})
        assert result["status"] == "completed"
        assert result["output"] == "output here"
        assert result["error_message"] == ""

    def test_returns_failed_on_nonzero_exit_code(self):
        svc, _ = _make_svc(exit_code=1, stdout="", stderr="traceback")
        result = svc.execute({"tool": "python_run", "input": {}})
        assert result["status"] == "failed"
        assert result["error_message"] == "traceback"

    def test_result_contains_job_id_and_session_id(self):
        svc, _ = _make_svc()
        result = svc.execute({"tool": "python_run", "input": {}, "session_id": "sess-abc"})
        assert result["session_id"] == "sess-abc"
        assert "job_id" in result
        assert len(result["job_id"]) > 0

    def test_duration_ms_is_non_negative(self):
        svc, _ = _make_svc()
        result = svc.execute({"tool": "python_run", "input": {}})
        assert result["duration_ms"] >= 0

    def test_raises_value_error_for_missing_tool(self):
        svc, _ = _make_svc()
        with pytest.raises(ValueError, match="Tool name is required"):
            svc.execute({"input": {}})

    def test_vm_is_always_released(self):
        """Even when vm.execute raises, release() must still be called."""
        mock_vm = MagicMock()
        mock_vm.execute.side_effect = RuntimeError("vm crash")
        mock_mgr = MagicMock()
        mock_mgr.acquire.return_value = mock_vm
        svc = ExecutionService(lifecycle_mgr=mock_mgr)
        with pytest.raises(RuntimeError, match="vm crash"):
            svc.execute({"tool": "python_run", "input": {}})
        mock_mgr.release.assert_called_once_with(mock_vm)

    def test_empty_input_defaults_to_empty_dict(self):
        svc, mock_vm = _make_svc()
        svc.execute({"tool": "python_run"})
        _, call_input = mock_vm.execute.call_args[0]
        assert call_input == {}


class TestExecutionServiceWithSimVM:
    """End-to-end test using _SimVM from VMLifecycleManager."""

    def test_sim_vm_execute_returns_valid_response(self, monkeypatch):
        monkeypatch.setenv("FC_MODE", "sim")
        from orchestrator.lifecycle import VMLifecycleManager, _SimVM

        mgr = VMLifecycleManager(
            storage=None,
            snapshot_name="test-snap",
            pool_size=1,
            firecracker_bin="/nonexistent/firecracker",
            dev_mode=False,
        )
        mgr.start()  # sim mode — should not raise

        vm = mgr.acquire()
        assert isinstance(vm, _SimVM)

        resp = vm.execute("python_run", {"code": "print('hello')"})
        assert resp.exit_code == 0
        assert "sim" in resp.stdout

        mgr.release(vm)  # no-op for _SimVM, must not raise
