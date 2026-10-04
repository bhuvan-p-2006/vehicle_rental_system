# syntax=docker/dockerfile:1.7
# Multi-stage build driven by uv (SPEC 13.1, 13.2, 13.6).
# Stage 1 resolves the lockfile into a virtualenv; the runtime stage copies only
# that virtualenv, so no compiler, lockfile, or dev group ships.
#
# Note: the plain `astral-sh/uv` images are distroless (no /bin/sh), so we use the
# `python3.x-<debian>` variant. psycopg2-binary ships prebuilt wheels, which is why
# no build toolchain is installed.

ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.7.2

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-bookworm-slim AS builder
ARG PYTHON_VERSION

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first so source edits do not invalidate the install layer.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root (SPEC 13.6).
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/app /app/app
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Migrations first, then seed, then serve — schema is always current on boot.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]