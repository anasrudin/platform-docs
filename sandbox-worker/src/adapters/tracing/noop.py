"""No-op Tracer untuk dev/testing tanpa OTel collector."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator


class _NoopSpan:
    def set_attribute(self, key: str, value: object) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def end(self) -> None:
        pass


class NoopTracer:
    @contextmanager
    def start_span(self, name: str, attributes: dict | None = None) -> Generator:
        yield _NoopSpan()
