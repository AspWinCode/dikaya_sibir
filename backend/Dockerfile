FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies for asyncpg and cryptography. `upgrade` pulls in
# any Debian security patches for packages already baked into the base
# image (not just the ones we're newly installing) — e.g. libpcre2's
# CVE-2026-103111 fix ships as a package upgrade, not a new install.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# ---- prod deps (no dev extras — faster, no conflicts from semgrep etc.) ----
FROM base AS deps
COPY pyproject.toml .
# Create a stub package so pip can install in non-editable mode without sources
RUN mkdir -p app && touch app/__init__.py && pip install .

# ---- dev deps (adds test/lint tooling on top) ----
FROM deps AS dev-deps
RUN pip install -e ".[dev]"

# ---- test (test deps + source; runs the suite) ----
# Kept BEFORE `runtime` so the default/last stage stays the production image
# (CI build + deploy build with no explicit target must produce `runtime`).
# Installs the minimal `.[test]` extra (NOT `.[dev]`, which is unresolvable due
# to semgrep's opentelemetry pin). Source is copied first so the editable
# install resolves the real package.
FROM deps AS test
COPY . .
RUN pip install -e ".[test]"
CMD ["sh", "scripts/run_tests.sh"]

# ---- runtime ----
FROM deps AS runtime
COPY . .

# Non-root user
RUN addgroup --gid 1001 appgroup \
    && adduser --uid 1001 --gid 1001 --disabled-password --gecos "" appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
