"""Observability setup for Party Sync (OTEL and Prometheus)."""

from __future__ import annotations

import os
from fastapi import FastAPI


def setup_observability(app: FastAPI, *, service_name: str) -> None:
    try:
        if os.environ.get("ENABLE_OTEL", "false").lower() in {"1", "true", "yes"}:
            _enable_tracing(service_name)
    except Exception:
        pass
    try:
        if os.environ.get("ENABLE_METRICS", "false").lower() in {"1", "true", "yes"}:
            _enable_metrics(app)
    except Exception:
        pass


def _enable_tracing(service_name: str) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    import os as _os

    endpoint = _os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "http://localhost:4318"
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument()
    RequestsInstrumentor().instrument()


def _enable_metrics(app: FastAPI) -> None:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)

