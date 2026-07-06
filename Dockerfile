# Stage 1: Build dependencies
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Accept the component name as a build argument
ARG COMPONENT

# 1. Copy workspace manifests
COPY pyproject.toml uv.lock* ./
COPY app/${COMPONENT}/pyproject.toml ./app/${COMPONENT}/

# 2. Install dependencies without caching the application source code yet
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --package ${COMPONENT}

# 3. Copy the actual application source code
COPY app/${COMPONENT}/ ./app/${COMPONENT}/

# 4. Final sync to include the application itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package ${COMPONENT}

# Stage 2: Tiny runtime image
FROM python:3.12-slim
WORKDIR /app
ARG COMPONENT
ENV COMPONENT_NAME=${COMPONENT}

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY app/${COMPONENT}/ ./app/${COMPONENT}/

# Use sh -c to evaluate the environment variable at runtime
CMD ["sh", "-c", "python app/${COMPONENT_NAME}/main.py"]
