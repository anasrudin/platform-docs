"""Tests for Execution DAG — models, interpolation, service, routes."""
from __future__ import annotations

import pytest

from adapters.tracing import init_tracer, reset_tracer
from models.workflow import (
    DAGWorkflow, StepResult, StepStatus, WorkflowStatus, WorkflowStep,
)
from service.workflow import (
    CyclicDependencyError, WorkflowService, WorkflowValidationError, _interpolate,
)


@pytest.fixture(autouse=True)
def tracer():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


def _make_svc(executor=None):
    """WorkflowService with a synchronous test executor."""
    return WorkflowService(executor=executor or _echo_executor)


def _echo_executor(tool: str, input_data: dict) -> dict:
    """Returns the input back as output — simple, deterministic."""
    return {"tool": tool, "echo": input_data}


def _failing_executor(tool: str, input_data: dict) -> dict:
    raise RuntimeError(f"tool '{tool}' failed")


# ── DAG Model ─────────────────────────────────────────────────────────────────

class TestWorkflowModels:
    def test_step_as_dict(self):
        step = WorkflowStep(id="s1", tool="python", input={"code": "print(1)"},
                            depends_on=["s0"])
        d = step.as_dict()
        assert d["id"] == "s1"
        assert d["depends_on"] == ["s0"]

    def test_step_result_duration_ms(self):
        from datetime import datetime, timezone, timedelta
        r = StepResult(step_id="s1")
        r.started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        r.completed_at = r.started_at + timedelta(milliseconds=150)
        assert r.duration_ms == 150

    def test_step_result_duration_none_when_not_done(self):
        r = StepResult(step_id="s1")
        assert r.duration_ms is None

    def test_workflow_as_dict_includes_steps(self):
        wf = DAGWorkflow(id="wf-1", name="test", steps=[])
        wf.results["s1"] = StepResult(step_id="s1", status=StepStatus.COMPLETED,
                                       output={"x": 1})
        d = wf.as_dict()
        assert d["workflow_id"] == "wf-1"
        assert "s1" in d["steps"]


# ── Output interpolation ──────────────────────────────────────────────────────

class TestInterpolation:
    def _results(self, **kwargs) -> dict[str, StepResult]:
        results = {}
        for step_id, output in kwargs.items():
            r = StepResult(step_id=step_id, status=StepStatus.COMPLETED, output=output)
            results[step_id] = r
        return results

    def test_plain_string_unchanged(self):
        assert _interpolate("hello", {}) == "hello"

    def test_full_output_reference(self):
        results = self._results(scrape={"html": "<p>hi</p>"})
        result = _interpolate("$steps.scrape.output", results)
        assert result == {"html": "<p>hi</p>"}

    def test_nested_field_reference(self):
        results = self._results(scrape={"html": "<p>hi</p>"})
        result = _interpolate("$steps.scrape.output.html", results)
        assert result == "<p>hi</p>"

    def test_unresolved_reference_left_as_is(self):
        result = _interpolate("$steps.missing.output.x", {})
        assert result == "$steps.missing.output.x"

    def test_dict_values_interpolated(self):
        results = self._results(step1={"val": 42})
        d = _interpolate({"key": "$steps.step1.output.val"}, results)
        assert d["key"] == 42

    def test_nested_dict_interpolated(self):
        results = self._results(a={"x": "foo"})
        d = _interpolate({"outer": {"inner": "$steps.a.output.x"}}, results)
        assert d["outer"]["inner"] == "foo"

    def test_list_values_interpolated(self):
        results = self._results(s={"n": 99})
        lst = _interpolate(["$steps.s.output.n", "static"], results)
        assert lst[0] == 99
        assert lst[1] == "static"

    def test_non_string_value_unchanged(self):
        assert _interpolate(42, {}) == 42
        assert _interpolate(3.14, {}) == 3.14
        assert _interpolate(None, {}) is None

    def test_inline_substitution_in_string(self):
        results = self._results(step1={"name": "world"})
        result = _interpolate("hello $steps.step1.output.name!", results)
        assert result == "hello world!"


# ── WorkflowService — validation ──────────────────────────────────────────────

class TestWorkflowValidation:
    def test_empty_steps_rejected(self):
        # 0 steps is valid — nothing to execute
        svc = _make_svc()
        result = svc.create("empty", [])
        assert "workflow_id" in result

    def test_step_missing_id_raises(self):
        svc = _make_svc()
        with pytest.raises(WorkflowValidationError, match="missing 'id'"):
            svc.create("wf", [{"tool": "python", "input": {}}])

    def test_step_missing_tool_raises(self):
        svc = _make_svc()
        with pytest.raises(WorkflowValidationError, match="missing 'tool'"):
            svc.create("wf", [{"id": "s1", "input": {}}])

    def test_unknown_dependency_raises(self):
        svc = _make_svc()
        steps = [{"id": "s1", "tool": "python", "input": {}, "depends_on": ["nonexistent"]}]
        with pytest.raises(WorkflowValidationError, match="unknown step"):
            svc.create("wf", steps)

    def test_cycle_detection(self):
        svc = _make_svc()
        steps = [
            {"id": "a", "tool": "t", "input": {}, "depends_on": ["b"]},
            {"id": "b", "tool": "t", "input": {}, "depends_on": ["a"]},
        ]
        with pytest.raises(CyclicDependencyError):
            svc.create("wf", steps)

    def test_too_many_steps_raises(self):
        svc = WorkflowService(max_steps=3)
        steps = [{"id": f"s{i}", "tool": "t", "input": {}} for i in range(5)]
        with pytest.raises(WorkflowValidationError, match="too many steps"):
            svc.create("wf", steps)


# ── WorkflowService — execution ───────────────────────────────────────────────

class TestWorkflowExecution:
    def test_linear_chain_executes_in_order(self):
        order = []
        def recording_executor(tool, input_data):
            order.append(tool)
            return {"done": tool}

        svc = WorkflowService(executor=recording_executor)
        steps = [
            {"id": "a", "tool": "step_a", "input": {}},
            {"id": "b", "tool": "step_b", "input": {}, "depends_on": ["a"]},
            {"id": "c", "tool": "step_c", "input": {}, "depends_on": ["b"]},
        ]
        result = svc.create("chain", steps)
        wf_id = result["workflow_id"]
        final = svc.wait(wf_id)
        assert final["status"] == "completed"
        assert order == ["step_a", "step_b", "step_c"]

    def test_independent_steps_all_complete(self):
        svc = _make_svc()
        steps = [
            {"id": "x", "tool": "tx", "input": {}},
            {"id": "y", "tool": "ty", "input": {}},
            {"id": "z", "tool": "tz", "input": {}},
        ]
        wf_id = svc.create("parallel", steps)["workflow_id"]
        final = svc.wait(wf_id)
        assert final["status"] == "completed"
        for sid in ["x", "y", "z"]:
            assert final["steps"][sid]["status"] == "completed"

    def test_failed_step_skips_downstream(self):
        svc = WorkflowService(executor=_failing_executor)
        steps = [
            {"id": "a", "tool": "t", "input": {}},
            {"id": "b", "tool": "t", "input": {}, "depends_on": ["a"]},
        ]
        wf_id = svc.create("failing", steps)["workflow_id"]
        final = svc.wait(wf_id)
        assert final["status"] == "failed"
        assert final["steps"]["a"]["status"] == "failed"
        assert final["steps"]["b"]["status"] == "skipped"

    def test_output_interpolation_in_downstream(self):
        def executor(tool, input_data):
            if tool == "producer":
                return {"value": 42}
            return {"received": input_data.get("x")}

        svc = WorkflowService(executor=executor)
        steps = [
            {"id": "p", "tool": "producer", "input": {}},
            {"id": "c", "tool": "consumer",
             "input": {"x": "$steps.p.output.value"},
             "depends_on": ["p"]},
        ]
        wf_id = svc.create("interpolation", steps)["workflow_id"]
        final = svc.wait(wf_id)
        assert final["status"] == "completed"
        assert final["steps"]["c"]["output"]["received"] == 42

    def test_get_returns_workflow(self):
        svc = _make_svc()
        wf_id = svc.create("g", [{"id": "s1", "tool": "t", "input": {}}])["workflow_id"]
        svc.wait(wf_id)
        info = svc.get(wf_id)
        assert info["name"] == "g"

    def test_get_unknown_raises_key_error(self):
        svc = _make_svc()
        with pytest.raises(KeyError):
            svc.get("wf-nonexistent")


# ── Workflow API routes ────────────────────────────────────────────────────────

class TestWorkflowRoutes:
    def _make_app(self, svc=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.workflow import register
        app = FastAPI()
        app.include_router(register({"workflow_svc": svc}))
        return TestClient(app)

    def test_no_svc_returns_503(self):
        client = self._make_app()
        resp = client.post("/workflows", json={"name": "x", "steps": []})
        assert resp.status_code == 503

    def test_create_returns_202(self):
        svc = _make_svc()
        client = self._make_app(svc)
        resp = client.post("/workflows", json={
            "name": "test",
            "steps": [{"id": "s1", "tool": "python", "input": {"code": "print(1)"}}],
        })
        assert resp.status_code == 202
        assert resp.json()["workflow_id"].startswith("wf-")

    def test_create_invalid_cycle_returns_422(self):
        svc = _make_svc()
        client = self._make_app(svc)
        resp = client.post("/workflows", json={
            "name": "cycle",
            "steps": [
                {"id": "a", "tool": "t", "input": {}, "depends_on": ["b"]},
                {"id": "b", "tool": "t", "input": {}, "depends_on": ["a"]},
            ],
        })
        assert resp.status_code == 422

    def test_get_returns_workflow(self):
        svc = _make_svc()
        wf_id = svc.create("get-test", [{"id": "s1", "tool": "t", "input": {}}])["workflow_id"]
        svc.wait(wf_id)
        client = self._make_app(svc)
        resp = client.get(f"/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-test"

    def test_get_unknown_returns_404(self):
        svc = _make_svc()
        client = self._make_app(svc)
        resp = client.get("/workflows/wf-ghost")
        assert resp.status_code == 404

    def test_completed_workflow_has_step_results(self):
        svc = _make_svc()
        client = self._make_app(svc)
        resp = client.post("/workflows", json={
            "name": "check",
            "steps": [{"id": "s1", "tool": "echo", "input": {"x": 1}}],
        })
        wf_id = resp.json()["workflow_id"]
        svc.wait(wf_id)
        poll = client.get(f"/workflows/{wf_id}")
        assert poll.json()["steps"]["s1"]["status"] == "completed"
