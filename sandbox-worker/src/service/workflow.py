"""WorkflowService — DAG execution with interpolation."""
from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

from models.workflow import (
    DAGWorkflow,
    StepResult,
    StepStatus,
    WorkflowStatus,
    WorkflowStep,
)

log = structlog.get_logger()


class WorkflowValidationError(ValueError):
    pass


class CyclicDependencyError(ValueError):
    pass


# ── Interpolation ─────────────────────────────────────────────────────────────

_REF_PATTERN = re.compile(r'\$steps\.([A-Za-z0-9_-]+)\.output((?:\.[A-Za-z0-9_-]+)*)')


def _resolve_ref(step_id: str, field_path: str, results: dict[str, StepResult]) -> Any:
    """Resolve $steps.step_id.output[.field...] → value, or original string if missing."""
    original = f"$steps.{step_id}.output{field_path}"
    result = results.get(step_id)
    if result is None or result.output is None:
        return original
    value = result.output
    if field_path:
        for field in field_path.lstrip(".").split("."):
            if isinstance(value, dict) and field in value:
                value = value[field]
            else:
                return original
    return value


def _interpolate(value: Any, results: dict[str, StepResult]) -> Any:
    """Recursively replace $steps.step_id.output[.field] references in value."""
    if isinstance(value, str):
        full = _REF_PATTERN.fullmatch(value)
        if full:
            return _resolve_ref(full.group(1), full.group(2), results)

        def _replace(m: re.Match) -> str:
            resolved = _resolve_ref(m.group(1), m.group(2), results)
            if resolved == f"$steps.{m.group(1)}.output{m.group(2)}":
                return m.group(0)
            return str(resolved)

        return _REF_PATTERN.sub(_replace, value)

    if isinstance(value, dict):
        return {k: _interpolate(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, results) for item in value]
    return value


# ── WorkflowService ───────────────────────────────────────────────────────────

class WorkflowService:
    _DEFAULT_MAX_STEPS = 20

    def __init__(
        self,
        executor: Callable[[str, dict], dict] | None = None,
        max_steps: int | None = None,
    ) -> None:
        self._executor = executor or _noop_executor
        self._max_steps = max_steps if max_steps is not None else self._DEFAULT_MAX_STEPS
        self._workflows: dict[str, DAGWorkflow] = {}

    def create(self, name: str, steps: list[dict]) -> dict:
        if len(steps) > self._max_steps:
            raise WorkflowValidationError(
                f"too many steps: {len(steps)} > {self._max_steps}"
            )

        step_ids: set[str] = set()
        parsed: list[WorkflowStep] = []
        for raw in steps:
            if "id" not in raw:
                raise WorkflowValidationError("missing 'id'")
            if "tool" not in raw:
                raise WorkflowValidationError("missing 'tool'")
            step_ids.add(raw["id"])
            parsed.append(
                WorkflowStep(
                    id=raw["id"],
                    tool=raw["tool"],
                    input=raw.get("input", {}),
                    depends_on=raw.get("depends_on", []),
                )
            )

        for step in parsed:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise WorkflowValidationError(
                        f"unknown step '{dep}' referenced in depends_on of '{step.id}'"
                    )

        waves = self._toposort(parsed)
        wf = DAGWorkflow(id=f"wf-{uuid.uuid4()}", name=name, steps=parsed)
        self._workflows[wf.id] = wf
        self._execute(wf, waves)
        return {"workflow_id": wf.id}

    def wait(self, workflow_id: str) -> dict:
        """Execution is synchronous; this just returns the current state."""
        return self.get(workflow_id)

    def get(self, workflow_id: str) -> dict:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            raise KeyError(f"Workflow {workflow_id!r} not found")
        return wf.as_dict()

    # ── private ────────────────────────────────────────────────────────────────

    def _toposort(self, steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
        """Kahn's algorithm — returns execution waves; raises CyclicDependencyError on cycle."""
        by_id = {s.id: s for s in steps}
        in_degree = {s.id: len(s.depends_on) for s in steps}
        dependents: dict[str, list[str]] = {s.id: [] for s in steps}

        for step in steps:
            for dep in step.depends_on:
                dependents[dep].append(step.id)

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        waves: list[list[WorkflowStep]] = []
        visited = 0

        while queue:
            wave_ids = list(queue)
            queue = []
            waves.append([by_id[sid] for sid in wave_ids])
            visited += len(wave_ids)
            for sid in wave_ids:
                for child_id in dependents[sid]:
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        queue.append(child_id)

        if visited < len(steps):
            raise CyclicDependencyError("cycle detected in workflow DAG")

        return waves

    def _can_run(self, step: WorkflowStep, results: dict[str, StepResult]) -> bool:
        return all(
            results.get(dep, StepResult(step_id=dep)).status == StepStatus.COMPLETED
            for dep in step.depends_on
        )

    def _run_step(self, step: WorkflowStep, results: dict[str, StepResult]) -> None:
        r = StepResult(step_id=step.id, status=StepStatus.RUNNING)
        r.started_at = datetime.now(timezone.utc)
        results[step.id] = r
        try:
            interpolated = _interpolate(step.input, results)
            r.output = self._executor(step.tool, interpolated)
            r.status = StepStatus.COMPLETED
        except Exception as exc:
            r.status = StepStatus.FAILED
            r.error = str(exc)
        finally:
            r.completed_at = datetime.now(timezone.utc)

    def _execute(self, wf: DAGWorkflow, waves: list[list[WorkflowStep]]) -> None:
        wf.status = WorkflowStatus.RUNNING
        results = wf.results

        for wave in waves:
            runnable = [s for s in wave if self._can_run(s, results)]
            for s in wave:
                if not self._can_run(s, results):
                    results[s.id] = StepResult(step_id=s.id, status=StepStatus.SKIPPED)

            if not runnable:
                continue

            if len(runnable) == 1:
                self._run_step(runnable[0], results)
            else:
                with ThreadPoolExecutor(max_workers=len(runnable)) as pool:
                    list(pool.map(lambda s: self._run_step(s, results), runnable))

        failed = any(r.status == StepStatus.FAILED for r in results.values())
        wf.status = WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
        wf.completed_at = datetime.now(timezone.utc)


def _noop_executor(tool: str, input_data: dict) -> dict:
    return {"tool": tool, "input": input_data}
