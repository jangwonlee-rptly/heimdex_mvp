# syntax=docker/dockerfile:1.7

# ---- Builder Stage ----
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv and create a virtual environment
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv venv ${VIRTUAL_ENV}

WORKDIR /app

# Copy dependency file and install dependencies
COPY pyproject.toml /app/
RUN uv sync --frozen --extra test --active || uv sync --extra test --active

# ---- Final Stage ----
FROM python:3.11-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:/home/appuser/.local/bin:${PATH}"

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -u 1000 appuser
WORKDIR /app

# Copy the virtual environment and application code from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser migrations /app/migrations
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini

USER appuser

# Default command launches the FastAPI service
CMD ["uv", "run", "--active", "fastapi", "run", "app/main.py", "--app", "app", "--host", "0.0.0.0", "--port", "8000"]
