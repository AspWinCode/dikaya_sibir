"""
OpenTelemetry setup — traces exported via OTLP (gRPC).

Instruments:
  - FastAPI (HTTP server spans)
  - SQLAlchemy async engine (DB query spans)

Configuration via environment variables (standard OTel conventions):
  OTEL_EXPORTER_OTLP_ENDPOINT  — default: http://localhost:4317
  OTEL_SERVICE_NAME            — default: nocode-platform
  OTEL_TRACES_SAMPLER          — default: parentbased_always_on
  APP_ENV=development          → no-op exporter (traces logged, not sent)

Usage in main.py lifespan:
    from app.core.telemetry import configure_telemetry
    configure_telemetry()
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_telemetry() -> None:
    """
    Initialize the global TracerProvider.

    In development (APP_ENV != production) a ConsoleSpanExporter is used
    so traces appear in logs without requiring a collector.
    In production, OTLP gRPC exporter sends to the configured endpoint.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        app_env = os.getenv("APP_ENV", "development")
        service_name = os.getenv("OTEL_SERVICE_NAME", "nocode-platform")

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if app_env == "production" and otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            logger.info("otel_otlp_exporter enabled: %s", otlp_endpoint)
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()  # type: ignore[assignment]
            logger.info("otel_console_exporter (dev or no OTLP endpoint)")

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    except ImportError as exc:
        logger.warning("otel_init_skipped: %s", exc)


def instrument_fastapi(app: object) -> None:
    """Attach FastAPI auto-instrumentation after app is created."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass


def instrument_sqlalchemy(engine: object) -> None:
    """Attach SQLAlchemy auto-instrumentation to the async engine."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except ImportError:
        pass


def get_tracer(name: str) -> object:
    """Convenience wrapper — returns a no-op tracer if OTel is not configured."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        import contextlib

        class _NoopTracer:
            def start_as_current_span(self, *a: object, **kw: object) -> object:
                return contextlib.nullcontext()

        return _NoopTracer()
