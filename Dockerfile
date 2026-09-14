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
COPY main.py ./
COPY mcp_server.py ./
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- frontend build (separate stage / service) ----
# docker build -f Dockerfile.frontend ./frontend
