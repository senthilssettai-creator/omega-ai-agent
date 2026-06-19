# OMEGA - Multi-stage production Dockerfile

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="OMEGA" \
      org.opencontainers.image.description="The Ultimate Open-Source Autonomous Terminal AI Agent" \
      org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN groupadd -r omega && useradd -r -g omega -m -d /home/omega omega

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/omega/.local/bin:$PATH \
    PYTHONPATH=/app \
    OMEGA_HOME=/home/omega/.omega

# Install runtime system dependencies (for Playwright browsers + git + docker CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/omega/.local

# Copy application code
COPY omega/ ./omega/
COPY pyproject.toml ./

RUN chown -R omega:omega /app /home/omega

USER omega

# Install Playwright browsers (as omega user)
RUN python -m playwright install chromium --with-deps 2>/dev/null || python -m playwright install chromium

RUN mkdir -p /home/omega/.omega/{plugins,memory,logs,sandbox,workflows}

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8888/health || exit 1

ENTRYPOINT ["python", "-m", "omega.cli"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8888"]
