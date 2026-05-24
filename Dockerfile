# syntax=docker/dockerfile:1.6

# ---- builder ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Wheels go into a single dir we copy in the runtime stage — keeps the final
# image small (no pip cache, no compiler toolchain).
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
 && pip wheel --wheel-dir /wheels -r requirements.txt \
 && apt-get purge -y --auto-remove gcc && rm -rf /var/lib/apt/lists/*

# ---- runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    LOG_FORMAT=json

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Install pre-built wheels — no compiler in the runtime image.
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

# Application code
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY pytest.ini .

# Telemetry SQLite (fallback) lives in /data so it can be on a Fly volume.
ENV TELEMETRY_DB_PATH=/data/heimdall.sqlite3
RUN mkdir -p /data && chown -R app:app /data /app

USER app
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# tini for proper signal handling, then run migrations and start uvicorn.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
