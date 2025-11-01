"""Observability setup: OpenTelemetry tracing and Prometheus metrics.

Включается через переменные окружения:
- ENABLE_OTEL=true — включает OpenTelemetry (OTLP exporter по OTEL_EXPORTER_OTLP_ENDPOINT)
- ENABLE_METRICS=true — включает Prometheus /metrics (prometheus-fastapi-instrumentator)
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI


def setup_observability(app: FastAPI, *, service_name: str) -> None:
    """Подключает трейсинг и метрики, если включено окружением.

    Args:
        app: экземпляр FastAPI.
        service_name: имя сервиса для Resource.
    """

    try:
        if os.environ.get("ENABLE_OTEL", "false").lower() in {"1", "true", "yes"}:
            _enable_tracing(service_name)
    except Exception:
        # Трассировка опциональна, не должна падать приложение
        pass

    try:
        if os.environ.get("ENABLE_METRICS", "false").lower() in {"1", "true", "yes"}:
            _enable_metrics(app)
    except Exception:
        # Метрики опциональны, не должны падать приложение
        pass


def _enable_tracing(service_name: str) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "http://localhost:4318"
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # ASGI/FastAPI и HTTP‑клиент
    FastAPIInstrumentor.instrument()
    RequestsInstrumentor().instrument()


def _enable_metrics(app: FastAPI) -> None:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)

