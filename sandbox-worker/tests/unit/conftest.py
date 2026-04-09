"""Shared pytest fixtures for unit tests."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from adapters.tracing.noop import _NoopSpan


class _RecordingSpan(_NoopSpan):
    """Span that captures set_attribute calls."""

    def __init__(self) -> None:
        self.attributes: dict = {}

    def set_attribute(self, key: str, value) -> None:
        self.attributes[key] = value


class RecordingTracer:
    """Test tracer that records all spans started, with their init attrs and span objects."""

    def __init__(self) -> None:
        # Each entry: (span_name, init_attrs_dict, _RecordingSpan)
        self.records: list[tuple[str, dict, _RecordingSpan]] = []

    @contextmanager
    def start_span(self, name: str, attributes: dict | None = None):
        span = _RecordingSpan()
        self.records.append((name, attributes or {}, span))
        yield span

    @property
    def spans(self) -> list[tuple[str, dict]]:
        """Convenience: list of (name, init_attrs) pairs, same as old API."""
        return [(r[0], r[1]) for r in self.records]


@pytest.fixture
def recording_tracer() -> RecordingTracer:
    return RecordingTracer()
