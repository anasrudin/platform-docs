# Build from repo root: docker build -f docker/fc-agent/Dockerfile .
FROM sandbox-base:latest

LABEL org.opencontainers.image.title="sandbox-fc-agent"
LABEL org.opencontainers.image.description="Firecracker microVM runtime worker"

# ── Firecracker + network deps ─────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    iptables \
    kmod \
    && rm -rf /var/lib/apt/lists/*

ARG FIRECRACKER_VERSION=v1.5.0
RUN curl -fsSL \
    "https://github.com/firecracker-microvm/firecracker/releases/download/${FIRECRACKER_VERSION}/firecracker-${FIRECRACKER_VERSION}-x86_64.tgz" \
    -o /tmp/firecracker.tgz \
    && tar -xzf /tmp/firecracker.tgz -C /tmp \
    && mv /tmp/release-${FIRECRACKER_VERSION}-x86_64/firecracker-${FIRECRACKER_VERSION}-x86_64 /usr/local/bin/firecracker \
    && chmod +x /usr/local/bin/firecracker \
    && rm -rf /tmp/firecracker.tgz /tmp/release-*

# /dev/kvm access — group added at runtime via Nomad device plugin
RUN usermod -aG kvm sandbox 2>/dev/null || true

USER sandbox
EXPOSE 8080

ENV RUNTIME_TIER=firecracker
ENV FIRECRACKER_BIN=/usr/local/bin/firecracker

CMD ["python3", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
