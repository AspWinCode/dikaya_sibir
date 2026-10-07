from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.telemetry import configure_telemetry, instrument_fastapi
from app.schemas.common import ErrorDetail, ProblemDetail

configure_logging()
logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Request metrics middleware
# ------------------------------------------------------------------


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Track HTTP request count and latency per (method, path, status).
    Uses prometheus_client histograms — complements business metrics
    defined in app.core.metrics.
    """

    from prometheus_client import Counter, Histogram

    _requests = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    _latency = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
    )

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        import time

        start = time.monotonic()
        response: Response = await call_next(request)
        duration = time.monotonic() - start

        # Normalise path: replace UUIDs with {id} to avoid high cardinality
        path = request.url.path
        self._requests.labels(
            method=request.method, path=path, status=str(response.status_code)
        ).inc()
        self._latency.labels(method=request.method, path=path).observe(duration)
        return response


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    # configure_telemetry initialises the TracerProvider (no middleware added here)
    configure_telemetry()
    logger.info("startup", env=settings.APP_ENV, version=settings.APP_VERSION)
    yield
    logger.info("shutdown")


# ------------------------------------------------------------------
# App factory
# ------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# Rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Middleware (order matters — outermost first)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenTelemetry FastAPI instrumentation — must happen BEFORE app starts
# (instrument_app adds middleware; adding after start raises RuntimeError)
instrument_fastapi(app)

# Prometheus /metrics scrape endpoint (separate ASGI app, no auth needed on internal port)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# ------------------------------------------------------------------
# Exception handlers
# ------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [ErrorDetail(loc=list(e["loc"]), msg=e["msg"], type=e["type"]) for e in exc.errors()]
    body = ProblemDetail(
        title="Validation Error",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Request body or query parameters failed validation.",
        instance=str(request.url),
        errors=errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=str(request.url), exc_info=exc)
    body = ProblemDetail(
        title="Internal Server Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        instance=str(request.url),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


app.include_router(api_router, prefix="/api/v1")
