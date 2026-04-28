# Multi-stage build for Naavik
# Stage 1: Builder - install dependencies with uv
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies into a virtual environment
RUN uv venv /app/.venv && \
    uv pip install --no-cache -e "." --python /app/.venv/bin/python

# Stage 2: Runtime - minimal image with app
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    typst \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/
COPY pyproject.toml ./

# Ensure the virtual environment is used
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Create generated directory for PDF output
RUN mkdir -p /app/generated

EXPOSE 8000

ENTRYPOINT ["fastapi", "run", "src/naavik/main.py"]
