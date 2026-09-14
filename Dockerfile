# ---- frontend (Node build stage; produces the SPA bundle) ----
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- backend ----
FROM python:3.11-slim AS backend
WORKDIR /app
# curl for HEALTHCHECK; non-root user for prod
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 appuser
COPY requirements-base.txt ./
RUN pip install --no-cache-dir -r requirements-base.txt
COPY backend ./backend
COPY config ./config
COPY scripts ./scripts
COPY static ./static
COPY main.py ./
COPY mcp_server.py ./
# SPA bundle built above (API serves it; static/ stays as fallback)
COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT:-8000}/health || exit 1
# Render/Docker pass $PORT; default 8000 for local docker run
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
