"""Tests — OTEL spans di SnapshotDownloader.ensure()."""
from __future__ import annotations

import pytest
from adapters.tracing import init_tracer, reset_tracer
from adapters.tracing.noop import _NoopSpan


class TestSnapshotSpans:
    def setup_method(self):
        reset_tracer()
        init_tracer(driver="noop")

    def teardown_method(self):
        reset_tracer()

    def test_ensure_cache_hit_emits_span(self, monkeypatch, tmp_path):
        """ensure() harus emit span vm.restore_snapshot saat cache hit."""
        import json
        from orchestrator.snapshot import SnapshotDownloader

        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append((name, attrs or {}))
                yield _NoopSpan()

        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: RecordingTracer())

        # Buat fake cached snapshot
        snap_dir = tmp_path / "mysnap"
        snap_dir.mkdir()
        (snap_dir / "vmstate.bin").write_bytes(b"state")
        (snap_dir / "memory.bin").write_bytes(b"mem")
        meta = {"name": "mysnap", "version": "1", "kernel": "", "rootfs": ""}
        (snap_dir / "meta.json").write_text(json.dumps(meta))

        class FakeStorage:
            def download(self, key): return b""

        dl = SnapshotDownloader(FakeStorage(), str(tmp_path))
        paths = dl.ensure("mysnap")

        assert paths is not None
        span_names = [s[0] for s in spans_started]
        assert "vm.restore_snapshot" in span_names

    def test_ensure_span_has_snapshot_name_attribute(self, monkeypatch, tmp_path):
        """Span vm.restore_snapshot harus punya attribute snapshot_name."""
        import json
        from orchestrator.snapshot import SnapshotDownloader

        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append((name, attrs or {}))
                yield _NoopSpan()

        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: RecordingTracer())

        snap_dir = tmp_path / "mysnap"
        snap_dir.mkdir()
        (snap_dir / "vmstate.bin").write_bytes(b"state")
        (snap_dir / "memory.bin").write_bytes(b"mem")
        meta = {"name": "mysnap", "version": "1", "kernel": "", "rootfs": ""}
        (snap_dir / "meta.json").write_text(json.dumps(meta))

        class FakeStorage:
            def download(self, key): return b""

        dl = SnapshotDownloader(FakeStorage(), str(tmp_path))
        dl.ensure("mysnap")

        snap_span = next(s for s in spans_started if s[0] == "vm.restore_snapshot")
        assert snap_span[1].get("snapshot_name") == "mysnap"
