# Build from repo root: docker build -f docker/office-agent/Dockerfile .
FROM sandbox-base:latest

LABEL org.opencontainers.image.title="sandbox-office-agent"
LABEL org.opencontainers.image.description="Office runtime worker — LibreOffice document processing"

# ── LibreOffice + fonts ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

ENV RUNTIME_TIER=office

USER sandbox
EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
