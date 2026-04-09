"""Tracing adapter — factory untuk mendapatkan tracer aktif.

Usage:
    from adapters.tracing import get_tracer

    tracer = get_tracer()
    with tracer.start_span("service.execution.route", {"tool": tool}) as span:
        ...
        span.set_attribute("tier", tier.value)

Driver dipilih lewat env var OTEL_DRIVER:
    noop   (default) — zero-overhead, cocok untuk dev
    otel   — kirim trace ke OTLP endpoint
"""
from __future__ import annotations

import os

from adapters.tracing.noop import NoopTracer

_tracer: NoopTracer | None = None


def get_tracer():
    """Return the process-level tracer singleton.

    Initialised on first call; subsequent calls return the same instance.
    Call init_tracer() early in lifespan to configure the real OTel tracer.
    """
    global _tracer
    if _tracer is None:
        _tracer = NoopTracer()
    return _tracer


def init_tracer(driver: str | None = None, service_name: str = "sandbox-platform", otlp_endpoint: str = ""):
    """Initialise the tracer singleton.  Call once during application startup."""
    global _tracer
    _driver = driver or os.environ.get("OTEL_DRIVER", "noop")
    if _driver == "otel":
        from adapters.tracing.otel import init_tracer as _init_otel
        _tracer = _init_otel(service_name, otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))
    else:
        _tracer = NoopTracer()
    return _tracer


def reset_tracer():
    """Reset singleton — test helper only."""
    global _tracer
    _tracer = None
