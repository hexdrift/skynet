# Air-gap operators: see AIRGAP.html for
# REGISTRY_PREFIX / DEBIAN_MIRROR / PIP_INDEX_URL / PIP_TRUSTED_HOST build-args.
# With those set nothing in this file fetches from public mirrors.
ARG REGISTRY_PREFIX=docker.io
FROM ${REGISTRY_PREFIX}/python:3.11-slim

WORKDIR /app

ARG DEBIAN_MIRROR
RUN if [ -n "$DEBIAN_MIRROR" ]; then \
        find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec \
            sed -i "s|http[s]\?://deb.debian.org|$DEBIAN_MIRROR|g; s|http[s]\?://security.debian.org|$DEBIAN_MIRROR|g" {} \; ; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
# Pinned install: requirements.txt captures the exact transitive wheel set, so
# every build resolves identically — the lockfile-equivalent guarantee. Kept in
# its own layer (before the source copy) so it caches until deps actually change.
RUN pip install --no-cache-dir \
        ${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL} \
        ${PIP_TRUSTED_HOST:+--trusted-host $PIP_TRUSTED_HOST} \
        -r requirements.txt

COPY . .

# Install the project itself editable, without re-resolving — every dependency
# is already pinned and present from the requirements.txt layer above.
RUN pip install --no-cache-dir --no-deps \
        ${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL} \
        ${PIP_TRUSTED_HOST:+--trusted-host $PIP_TRUSTED_HOST} \
        -e .

ARG GIT_SHA=unknown

# Use UID 1001 with GID 0 — works everywhere (Docker, Podman, OpenShift restricted-v2 SCC).
# OpenShift assigns a random UID at runtime but always with GID 0, so /app must be
# group-0-owned and group-writable for the editable install metadata to be accessible.
RUN groupadd -g 1001 appuser 2>/dev/null || true \
    && useradd -u 1001 -g 0 -m -s /sbin/nologin appuser \
    && chgrp -R 0 /app \
    && chmod -R g=u /app

USER 1001

ENV PYTHONUNBUFFERED=1
ENV WORKER_CONCURRENCY=4
ENV WORKER_POLL_INTERVAL=2.0
ENV SKYNET_CODE_VERSION=$GIT_SHA
ENV LOG_LEVEL=INFO
# Containerized runs default to structured logs; override to "text" only
# when running the image interactively for debugging.
ENV LOG_FORMAT=json
# air-gap — litellm uses its bundled cost map instead of fetching model_prices_and_context_window.json from GitHub on import.
ENV LITELLM_LOCAL_MODEL_COST_MAP=True
# Recommendation embeddings are served by an internal OpenAI-compatible API;
# no model weights are loaded inside the backend container.
# REMOTE_DB_URL must be set at runtime (e.g., via docker-compose or -e flag)
# ENV REMOTE_DB_URL=postgresql://user:password@host:5432/skynet

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
