# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:/home/appuser/.local/bin:/root/.local/bin:${PATH}"

# System deps: ffmpeg/ffprobe + build essentials (kept slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        gcc \
        libffi-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast package manager from Astral)
# https://docs.astral.sh/uv/
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv managed by uv
RUN uv venv ${VIRTUAL_ENV}

# Workdir & non-root user (optional but recommended)
WORKDIR /app
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /opt/venv

# Install uv for the appuser as well
USER appuser
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy only dependency file first for layer caching
COPY --chown=appuser:appuser pyproject.toml /app/pyproject.toml

# Install deps into the venv (no dev extras yet)
RUN uv sync --frozen --active || uv sync --active

# Now copy source
COPY --chown=appuser:appuser app /app/app

# Default command shows tool versions (you can override in docker-compose)
CMD ["uv", "run", "--active", "python", "app/cli.py", "--check"]
