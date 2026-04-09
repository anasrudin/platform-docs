"""Tests — OTEL spans di SnapshotDownloader.ensure()."""
from __future__ import annotations

import json

from adapters.tracing import reset_tracer
from orchestrator.snapshot import SnapshotDownloader
from tests.unit.conftest import RecordingTracer


class _MetaStorage:
    """Storage that returns valid blobs for any key."""

    def download(self, key: str) -> bytes:
        if key.endswith("meta.json"):
            name = key.split("/")[0]
            return json.dumps(
                {"name": name, "version": "1", "kernel": "", "rootfs": ""}
            ).encode()
        return b"\x00" * 8


class TestSnapshotSpans:
    def setup_method(self):
        reset_tracer()

    def teardown_method(self):
        reset_tracer()

    def test_cache_hit_emits_restore_snapshot_span(self, monkeypatch, tmp_path):
        """ensure() harus emit span vm.restore_snapshot saat cache hit."""
        tracer = RecordingTracer()
        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: tracer)

        snap_dir = tmp_path / "mysnap"
        snap_dir.mkdir()
        (snap_dir / "vmstate.bin").write_bytes(b"state")
        (snap_dir / "memory.bin").write_bytes(b"mem")
        (snap_dir / "meta.json").write_text(
            json.dumps({"name": "mysnap", "version": "1", "kernel": "", "rootfs": ""})
        )

        dl = SnapshotDownloader(_MetaStorage(), str(tmp_path))
        paths = dl.ensure("mysnap")

        assert paths is not None
        span_names = [r[0] for r in tracer.records]
        assert "vm.restore_snapshot" in span_names

    def test_cache_hit_span_has_snapshot_name_attribute(self, monkeypatch, tmp_path):
        """Span vm.restore_snapshot harus punya attribute snapshot_name."""
        tracer = RecordingTracer()
        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: tracer)

        snap_dir = tmp_path / "mysnap"
        snap_dir.mkdir()
        (snap_dir / "vmstate.bin").write_bytes(b"state")
        (snap_dir / "memory.bin").write_bytes(b"mem")
        (snap_dir / "meta.json").write_text(
            json.dumps({"name": "mysnap", "version": "1", "kernel": "", "rootfs": ""})
        )

        dl = SnapshotDownloader(_MetaStorage(), str(tmp_path))
        dl.ensure("mysnap")

        snap_record = next(r for r in tracer.records if r[0] == "vm.restore_snapshot")
        assert snap_record[1].get("snapshot_name") == "mysnap"

    def test_cache_miss_span_has_cache_hit_false(self, monkeypatch, tmp_path):
        """ensure() harus set cache_hit=False di span saat blobs tidak ada di cache."""
        tracer = RecordingTracer()
        monkeypatch.setattr("orchestrator.snapshot.get_tracer", lambda: tracer)

        # No files pre-created → cache miss path
        dl = SnapshotDownloader(_MetaStorage(), str(tmp_path))
        dl.ensure("newsnap")

        snap_record = next(r for r in tracer.records if r[0] == "vm.restore_snapshot")
        span = snap_record[2]
        assert span.attributes.get("cache_hit") is False
