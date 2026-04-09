"""Unit tests for sandbox_platform.router."""

from unittest.mock import MagicMock
from datetime import datetime, timezone


from service.router import Router, default_rules
from models.job import Job, JobStatus, RuntimeResult
from models.session import Tier


def _make_queue_client(result: RuntimeResult | None = None, timeout: bool = False):
    qc = MagicMock()
    qc.push_job.return_value = None
    if timeout:
        qc.wait_for_job_result.side_effect = TimeoutError("timeout")
    else:
        qc.wait_for_job_result.return_value = result or RuntimeResult(
            stdout="ok", exit_code=0
        )
    return qc


def _make_job(tool: str = "echo") -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id="j1",
        session_id="s1",
        tool=tool,
        tier=Tier.WASM,
        input={"x": 1},
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


class TestDefaultRules:
    def test_wasm_tools(self):
        rules = default_rules()
        for tool in ("echo", "hello", "json_parse", "html_parse", "markdown_convert"):
            assert rules[tool] is Tier.WASM, f"{tool} should be WASM"

    def test_microvm_tools(self):
        rules = default_rules()
        for tool in ("python_run", "bash_run", "git_clone", "file_ops"):
            assert rules[tool] is Tier.MICROVM, f"{tool} should be MICROVM"

    def test_gui_tools(self):
        rules = default_rules()
        for tool in ("browser_open", "web_scrape", "excel_edit", "office_automation"):
            assert rules[tool] is Tier.GUI, f"{tool} should be GUI"


class TestRouter:
    def test_resolve_known_tool(self):
        qc = _make_queue_client()
        router = Router(qc)
        assert router.resolve("echo") is Tier.WASM
        assert router.resolve("python_run") is Tier.MICROVM
        assert router.resolve("browser_open") is Tier.GUI

    def test_resolve_unknown_defaults_to_wasm(self):
        qc = _make_queue_client()
        router = Router(qc)
        assert router.resolve("unknown_tool_xyz") is Tier.WASM

    def test_register_overrides_rule(self):
        qc = _make_queue_client()
        router = Router(qc)
        router.register("echo", Tier.MICROVM)
        assert router.resolve("echo") is Tier.MICROVM

    def test_execute_calls_push_and_wait(self):
        expected = RuntimeResult(stdout="hello", exit_code=0)
        qc = _make_queue_client(result=expected)
        router = Router(qc)
        job = _make_job("echo")

        result = router.execute(job)

        qc.push_job.assert_called_once()
        qc.wait_for_job_result.assert_called_once_with(job.id, timeout=30.0)
        assert result.stdout == "hello"
        assert result.exit_code == 0

    def test_execute_sets_tier_on_job(self):
        qc = _make_queue_client()
        router = Router(qc)
        job = _make_job("python_run")
        job.tier = Tier.WASM  # wrong tier initially

        router.execute(job)

        pushed_job = qc.push_job.call_args[0][0]
        assert pushed_job.tier is Tier.MICROVM

    def test_execute_timeout_returns_error_result(self):
        qc = _make_queue_client(timeout=True)
        router = Router(qc)
        job = _make_job("echo")

        result = router.execute(job)

        assert result.exit_code == 1
        assert "timeout" in result.stderr.lower()

    def test_thread_safety_register_resolve(self):
        import threading

        qc = _make_queue_client()
        router = Router(qc)
        errors = []

        def writer():
            for i in range(100):
                try:
                    router.register(f"tool_{i}", Tier.WASM)
                except Exception as exc:
                    errors.append(exc)

        def reader():
            for i in range(100):
                try:
                    router.resolve(f"tool_{i}")
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
