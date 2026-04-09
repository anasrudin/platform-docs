"""OpenTelemetry Tracer — exports to OTLP endpoint."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from opentelemetry import trace  # type: ignore[import]
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore[import]
from opentelemetry.sdk.resources import Resource  # type: ignore[import]
from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import]
from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import]


def init_tracer(service_name: str, otlp_endpoint: str) -> "OTelTracer":
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    trace.set_tracer_provider(provider)
    return OTelTracer(trace.get_tracer(service_name))


class OTelTracer:
    def __init__(self, tracer: trace.Tracer) -> None:
        self._tracer = tracer

    @contextmanager
    def start_span(self, name: str, attributes: dict | None = None) -> Generator:
        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
            try:
                yield span
            except Exception as exc:
                span.record_exception(exc)
                raise
