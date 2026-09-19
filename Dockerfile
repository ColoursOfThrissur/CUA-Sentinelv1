# ==============================================================================
# Multi-Stage Dockerfile for CUA-Sentinel (Frontend Build + FastAPI Runtime)
# ==============================================================================

# --- Stage 1: Frontend Build ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Stage 2: Backend Runtime ---
FROM python:3.12-slim AS runner
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source & configs
COPY backend/ ./backend/
COPY data/ ./data/

# Copy built frontend assets into frontend/dist for FastAPI SPA static hosting
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose FastAPI port
EXPOSE 8000

# Health probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch FastAPI backend
CMD ["python", "backend/main.py"]
