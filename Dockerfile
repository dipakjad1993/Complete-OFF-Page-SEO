# ---- backend ----
FROM python:3.11-slim AS backend
WORKDIR /app
COPY requirements-base.txt ./
RUN pip install --no-cache-dir -r requirements-base.txt
COPY backend ./backend
COPY config ./config
COPY scripts ./scripts
COPY main.py ./
COPY mcp_server.py ./
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- frontend build (separate stage / service) ----
# docker build -f Dockerfile.frontend ./frontend
