"""Unit tests for sandbox_platform.runtime.gui.runtime."""

import json
from datetime import datetime, timezone


from runtime.gui import Runtime
from models.job import Job, JobStatus
from models.session import Tier


def _make_job(tool: str, input_data: dict = None) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id="j-gui-01234567",  # needs at least 8 chars for slicing
        session_id="s1",
        tool=tool,
        tier=Tier.GUI,
        input=input_data or {},
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


class TestGUIRuntime:
    def test_name(self):
        rt = Runtime()
        assert rt.name() == "gui-runtime-stub"

    def test_tier(self):
        rt = Runtime()
        assert rt.tier() is Tier.GUI

    def test_health_no_error(self):
        rt = Runtime()
        rt.health()

    def test_execute_returns_success(self):
        rt = Runtime()
        job = _make_job("browser_open", {"url": "https://example.com"})
        result = rt.execute(job)
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_execute_output_is_valid_json(self):
        rt = Runtime()
        job = _make_job("web_scrape", {"url": "https://example.com"})
        result = rt.execute(job)
        data = json.loads(result.stdout)
        assert data["status"] == "completed"
        assert data["runtime"] == "gui-stub"

    def test_execute_result_contains_metadata(self):
        rt = Runtime()
        job = _make_job("browser_open")
        result = rt.execute(job)
        data = json.loads(result.stdout)
        assert "metadata" in data
        assert data["metadata"]["browser"] == "chromium-121"
        assert "stream_url" in data["metadata"]

    def test_execute_session_id_uses_job_id_prefix(self):
        rt = Runtime()
        job = _make_job("excel_edit")
        result = rt.execute(job)
        data = json.loads(result.stdout)
        assert data["session_id"].startswith("browser-")
        assert job.id[:8] in data["session_id"]

    def test_execute_reflects_tool_in_output(self):
        rt = Runtime()
        job = _make_job("office_automation")
        result = rt.execute(job)
        data = json.loads(result.stdout)
        assert data["tool"] == "office_automation"
