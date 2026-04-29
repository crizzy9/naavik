# Naavik — multi-stage build
# Stage 1: Builder — install deps via uv against the locked uv.lock
FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Reproducible install from uv.lock (frozen = error on drift; --no-dev = production deps only)
RUN uv sync --frozen --no-dev

# Stage 2: Runtime — minimal image with venv + source + migrations
FROM python:3.12-slim AS runtime

WORKDIR /app

# Typst for PDF generation; create state dir
RUN apt-get update \
    && apt-get install -y --no-install-recommends typst \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/.naavik

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src ./src
COPY --from=builder /app/pyproject.toml /app/uv.lock ./
COPY migrations/ ./migrations/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

EXPOSE 8000

ENTRYPOINT ["fastapi", "run", "src/main.py"]
