# Stage 1: Build dependencies
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# 1. Copy workspace manifests first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./
COPY app/adsb-api/pyproject.toml ./app/adsb-api/

# 2. Install dependencies without caching the application source code yet
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --package adsb-api

# 3. Copy the actual application source code
COPY app/adsb-api/ ./app/adsb-api/

# 4. Final sync to include the application itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package adsb-api

# Stage 2: Tiny runtime image
FROM python:3.12-slim
WORKDIR /app

# Copy the pre-compiled virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# Ensure Python outputs logs immediately without buffering
ENV PYTHONUNBUFFERED=1

# Copy the actual source code
COPY app/adsb-api/ ./adsb-api

# Fallback, will be overridden by k8s
CMD ["python", "adsb-api/main.py"]
