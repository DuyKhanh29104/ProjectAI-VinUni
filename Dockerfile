# syntax=docker/dockerfile:1

# ---- Shared system runtime ----
FROM python:3.12-slim AS base

# OpenCV is pulled by Ultralytics and requires these shared libraries even for
# headless CPU inference on Debian slim.
RUN apt-get update && \
    apt-get install --no-install-recommends -y libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# ---- Stage 1: Build ----
FROM base AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY pyproject.toml README.md ./
# The API owns private GCS streaming and the interactive Label QA Agent.
# Browser/downloader dependencies remain isolated in the ingestion worker.
# Install CPU-only PyTorch first. The default Linux wheel can pull a multi-GB
# CUDA toolkit even though the Railway web service has no GPU.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision && \
    pip install ".[cloud,agent-yolo]"

# Application source is copied only into the final image. Keeping it out of the
# dependency layer lets ordinary code changes reuse the expensive CPU inference
# dependency cache.

# Bundle the small CPU-safe checkpoint in the image. This avoids a slow and
# failure-prone model download on the first request of every Railway replica.
RUN mkdir -p /models && \
    python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')" && \
    mv /app/yolo26n.pt /models/yolo26n.pt

# ---- Stage 2: Production ----
FROM base AS production

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    YOLO_CONFIG_DIR=/home/appuser/.config \
    YOLO_MODEL_NAME=/app/models/yolo26n.pt

# Copy the self-contained Python environment and bundled model from builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /models /app/models

# Security: run as non-root user
RUN useradd -m appuser && \
    mkdir -p /home/appuser/.config/Ultralytics && \
    chown -R appuser:appuser /home/appuser

# Copy application code
COPY --chown=appuser:appuser . .

# Prepare the ephemeral GCS cache and normalize the startup script copied from
# cross-platform worktrees. Production may mount a persistent cache here, but
# the image never bundles or depends on workspace dataset files.
RUN mkdir -p /app/data && \
    sed -i 's/\r$//' /app/scripts/start_server.sh && \
    chmod +x /app/scripts/start_server.sh && \
    chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://localhost:{os.getenv('PORT', '8000')}/ready\")" || exit 1

CMD ["/app/scripts/start_server.sh"]
