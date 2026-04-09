"""Tracer Protocol — distributed tracing abstraction."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Protocol


class Span(Protocol):
    def set_attribute(self, key: str, value: object) -> None: ...
    def record_exception(self, exc: Exception) -> None: ...
    def end(self) -> None: ...


class Tracer(Protocol):
    @contextmanager
    def start_span(self, name: str, attributes: dict | None = None) -> Generator[Span, None, None]: ...
