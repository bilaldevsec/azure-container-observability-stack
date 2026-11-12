# ==============================================================================
# CloudNotes Observability Microservice Dockerfile
# Production-grade multi-stage / non-root security container pattern
# ==============================================================================

FROM python:3.12-slim

# Set environment variables for Python in containerized environments
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Set working directory
WORKDIR /app

# Install curl for reliable container health checking and clean package caches
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python requirements cleanly without pip cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create an unprivileged user and group for defense-in-depth container security
RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -s /bin/bash -m appuser

# Copy application source code and adjust ownership
COPY main.py .
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose microservice HTTP port
EXPOSE 8000

# Container healthcheck: pings /health endpoint every 15 seconds
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn ASGI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
