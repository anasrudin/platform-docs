# Build from repo root: docker build -f docker/gui-agent/Dockerfile .
FROM sandbox-base:latest

LABEL org.opencontainers.image.title="sandbox-gui-agent"
LABEL org.opencontainers.image.description="GUI runtime worker — Chromium + Playwright + Xvfb"

# ── Display server + browser ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    xdotool \
    chromium-browser \
    chromium-chromedriver \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# ── Playwright — use system Chromium, skip browser download ───────────────────
RUN pip3 install --no-cache-dir playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin

ENV DISPLAY=:99
ENV RUNTIME_TIER=gui

USER sandbox
EXPOSE 8080 5900

CMD ["python3", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
