ARG REGISTRY_PREFIX=docker.io
FROM ${REGISTRY_PREFIX}/python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY server.py /app/server.py

EXPOSE 9000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9000", "--log-level", "warning"]
