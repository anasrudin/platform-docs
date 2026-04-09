"""Tests for Session Hibernation — service, orchestrator, models, and API routes."""
from __future__ import annotations

import time

import pytest

from adapters.tracing import init_tracer, reset_tracer
from models.hibernation import HibernateState, HibernateSnapshot, RestoreResult


@pytest.fixture(autouse=True)
def reset_tracer_fixture():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


# ── HibernationOrchestrator ────────────────────────────────────────────────────

class TestHibernationOrchestrator:
    def _make_orch(self):
        from orchestrator.hibernation import HibernationOrchestrator

        class MemStorage:
            def __init__(self):
                self._data: dict[str, bytes] = {}
            def upload(self, key, data, **kw):
                self._data[key] = data
                return key
            def download(self, key):
                if key not in self._data:
                    raise FileNotFoundError(key)
                return self._data[key]

        storage = MemStorage()
        orch = HibernationOrchestrator(storage, sim_mode=True)
        return orch, storage

    def test_hibernate_returns_snapshot(self):
        orch, _ = self._make_orch()
        snap = orch.hibernate("sess-1")
        assert isinstance(snap, HibernateSnapshot)
        assert snap.session_id == "sess-1"
        assert snap.snapshot_key == "hibernate/sess-1"

    def test_restore_returns_result(self):
        orch, _ = self._make_orch()
        orch.hibernate("sess-1")
        result = orch.restore("sess-1", "hibernate/sess-1")
        assert isinstance(result, RestoreResult)
        assert result.session_id == "sess-1"
        assert result.restored_from == "hibernate/sess-1"
        assert result.restore_ms >= 0

    def test_hibernate_sets_hibernated_at(self):
        from datetime import datetime
        orch, _ = self._make_orch()
        snap = orch.hibernate("sess-1")
        assert isinstance(snap.hibernated_at, datetime)

    def test_sim_mode_skips_storage_calls(self):
        from orchestrator.hibernation import HibernationOrchestrator

        class StrictStorage:
            def upload(self, *a, **kw):
                raise AssertionError("should not be called in sim mode")
            def download(self, *a, **kw):
                raise AssertionError("should not be called in sim mode")

        orch = HibernationOrchestrator(StrictStorage(), sim_mode=True)
        orch.hibernate("sess-sim")  # must not raise


# ── HibernationService ────────────────────────────────────────────────────────

class TestHibernationService:
    def _make_svc(self, **kwargs):
        from service.hibernation import HibernationService
        from orchestrator.hibernation import HibernationOrchestrator

        class MemStorage:
            def __init__(self):
                self._data: dict[str, bytes] = {}
            def upload(self, key, data, **kw):
                self._data[key] = data
                return key
            def download(self, key):
                return self._data.get(key, b"")

        orch = HibernationOrchestrator(MemStorage(), sim_mode=True)
        return HibernationService(orch, **kwargs)

    def test_initial_state_is_active(self):
        svc = self._make_svc()
        assert svc.state("sess-1") == HibernateState.ACTIVE

    def test_touch_marks_active(self):
        svc = self._make_svc()
        svc.touch("sess-1")
        assert svc.state("sess-1") == HibernateState.ACTIVE

    def test_hibernate_changes_state_to_hibernated(self):
        svc = self._make_svc()
        svc.touch("sess-1")
        svc.hibernate("sess-1")
        assert svc.state("sess-1") == HibernateState.HIBERNATED

    def test_hibernate_returns_dict_with_expected_keys(self):
        svc = self._make_svc()
        result = svc.hibernate("sess-1")
        assert "hibernated_at" in result
        assert "snapshot_key" in result
        assert "sess-1" in result["snapshot_key"]

    def test_restore_after_hibernate_returns_to_active(self):
        svc = self._make_svc()
        svc.hibernate("sess-1")
        svc.restore("sess-1")
        assert svc.state("sess-1") == HibernateState.ACTIVE

    def test_restore_without_snapshot_raises_key_error(self):
        svc = self._make_svc()
        with pytest.raises(KeyError):
            svc.restore("no-such-session")

    def test_restore_returns_dict_with_restore_ms(self):
        svc = self._make_svc()
        svc.hibernate("sess-2")
        result = svc.restore("sess-2")
        assert "restore_ms" in result
        assert isinstance(result["restore_ms"], int)

    def test_scan_idle_hibernates_timed_out_sessions(self):
        svc = self._make_svc(idle_timeout=0)  # instant timeout
        svc.touch("sess-idle")
        time.sleep(0.01)
        hibernated = svc.scan_idle()
        assert "sess-idle" in hibernated
        assert svc.state("sess-idle") == HibernateState.HIBERNATED

    def test_scan_idle_skips_already_hibernated(self):
        svc = self._make_svc(idle_timeout=0)
        svc.touch("sess-1")
        svc.hibernate("sess-1")
        hibernated = svc.scan_idle()
        assert "sess-1" not in hibernated

    def test_scan_idle_skips_active_within_timeout(self):
        svc = self._make_svc(idle_timeout=9999)
        svc.touch("sess-fresh")
        hibernated = svc.scan_idle()
        assert "sess-fresh" not in hibernated

    def test_cleanup_expired_removes_old_snapshots(self):
        from datetime import datetime, timedelta, timezone
        svc = self._make_svc()
        svc.hibernate("sess-exp")
        # Manually set expires_at to the past
        snap = svc._snapshots["sess-exp"]
        snap.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        cleaned = svc.cleanup_expired()
        assert "sess-exp" in cleaned
        assert "sess-exp" not in svc._snapshots


# ── Hibernation API routes ────────────────────────────────────────────────────

class TestHibernationRoutes:
    def _make_app(self, hibernation_svc=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.hibernation import register

        app = FastAPI()
        state = {"hibernation_svc": hibernation_svc}
        app.include_router(register(state))
        return TestClient(app)

    def test_hibernate_disabled_returns_503(self):
        client = self._make_app(hibernation_svc=None)
        resp = client.post("/sessions/sess-1/hibernate")
        assert resp.status_code == 503

    def test_restore_disabled_returns_503(self):
        client = self._make_app(hibernation_svc=None)
        resp = client.post("/sessions/sess-1/restore")
        assert resp.status_code == 503

    def test_hibernate_returns_202_with_snapshot_key(self):
        from service.hibernation import HibernationService
        from orchestrator.hibernation import HibernationOrchestrator

        class Mem:
            def upload(self, k, d, **kw): return k
            def download(self, k): return b""

        svc = HibernationService(HibernationOrchestrator(Mem(), sim_mode=True))
        client = self._make_app(hibernation_svc=svc)
        resp = client.post("/sessions/sess-abc/hibernate")
        assert resp.status_code == 202
        body = resp.json()
        assert "snapshot_key" in body
        assert "hibernated_at" in body

    def test_restore_returns_200_with_restore_ms(self):
        from service.hibernation import HibernationService
        from orchestrator.hibernation import HibernationOrchestrator

        class Mem:
            def upload(self, k, d, **kw): return k
            def download(self, k): return b""

        svc = HibernationService(HibernationOrchestrator(Mem(), sim_mode=True))
        svc.hibernate("sess-abc")
        client = self._make_app(hibernation_svc=svc)
        resp = client.post("/sessions/sess-abc/restore")
        assert resp.status_code == 200
        assert "restore_ms" in resp.json()

    def test_restore_unknown_session_returns_404(self):
        from service.hibernation import HibernationService
        from orchestrator.hibernation import HibernationOrchestrator

        class Mem:
            def upload(self, k, d, **kw): return k
            def download(self, k): return b""

        svc = HibernationService(HibernationOrchestrator(Mem(), sim_mode=True))
        client = self._make_app(hibernation_svc=svc)
        resp = client.post("/sessions/no-such-session/restore")
        assert resp.status_code == 404
