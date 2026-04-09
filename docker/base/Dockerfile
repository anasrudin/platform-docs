FROM ubuntu:22.04

LABEL org.opencontainers.image.vendor="sandbox-platform"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# ── System packages (shared) ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    python3-venv \
    iproute2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    structlog \
    httpx \
    minio \
    python-consul \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp

# ── Application source ─────────────────────────────────────────────────────────
# Build context harus dari repo root: docker build -f docker/base/Dockerfile .
COPY sandbox-worker/src/ /app/src/

RUN useradd -m -u 1000 sandbox
WORKDIR /app
