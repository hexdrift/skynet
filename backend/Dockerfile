# TODO: On-premise - Update base image to use internal registry
# Example: FROM artifactory.your-company.com/docker-remote/python:3.11-slim
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# TODO: On-premise - Configure pip to use local artifactory
# Example: RUN pip config set global.index-url https://artifactory.your-company.com/api/pypi/pypi-remote/simple

# Copy dependency files first for better caching
COPY pyproject.toml ./

# Install dependencies
RUN pip install -e .

# Copy application code
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV WORKER_CONCURRENCY=2
ENV WORKER_POLL_INTERVAL=2.0
ENV LOG_LEVEL=INFO
# REMOTE_DB_URL must be set at runtime (e.g., via docker-compose or -e flag)
# ENV REMOTE_DB_URL=postgresql://user:password@host:5432/skynet

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
