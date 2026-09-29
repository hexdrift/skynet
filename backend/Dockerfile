# Air-gap operators: see AIRGAP.html for REGISTRY_PREFIX / DEBIAN_MIRROR /
# PIP_INDEX_URL / PIP_TRUSTED_HOST build-args, plus DENO_DOWNLOAD_BASE /
# NPM_CONFIG_REGISTRY for the Flex module's Deno sandbox.
# With those set nothing in this file fetches from public mirrors.
ARG REGISTRY_PREFIX=docker.io
# 3.12 for PEP 683 immortal objects: core interpreter objects stop taking
# refcount writes, so job children fork()ed from the fat parent dirty far
# fewer copy-on-write pages. Full test suite verified green on 3.12.
FROM ${REGISTRY_PREFIX}/python:3.12-slim

WORKDIR /app

ARG DEBIAN_MIRROR
RUN if [ -n "$DEBIAN_MIRROR" ]; then \
        find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec \
            sed -i "s|http[s]\?://deb.debian.org|$DEBIAN_MIRROR|g; s|http[s]\?://security.debian.org|$DEBIAN_MIRROR|g" {} \; ; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl unzip \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock requirements.txt ./

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
# Dependency installer toggle. PKG_MANAGER=uv (default) installs the exact
# uv.lock wheel set via uv. PKG_MANAGER=pip installs requirements.txt, the same
# set exported from uv.lock, for hosts without uv:
#   docker build --build-arg PKG_MANAGER=pip ...
# Either way the deps land in their own layer (before the source copy) so it
# caches until the lockfile / requirements change. requirements.txt is a
# complete compiled lockfile, so we install with --no-deps to skip
# re-resolution; the pip-path image smoke tests in CI check the set is complete.
ARG PKG_MANAGER=uv
RUN if [ "$PKG_MANAGER" = "pip" ]; then \
        pip install --no-cache-dir --no-deps \
            ${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL} \
            ${PIP_TRUSTED_HOST:+--trusted-host $PIP_TRUSTED_HOST} \
            -r requirements.txt; \
    else \
        pip install --no-cache-dir \
            ${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL} \
            ${PIP_TRUSTED_HOST:+--trusted-host $PIP_TRUSTED_HOST} \
            uv \
        && UV_INDEX_URL=${PIP_INDEX_URL:-} \
           UV_PYTHON_DOWNLOADS=never \
           uv sync --frozen --no-install-project; \
    fi

# dspy.Flex serve-time dependency. An optimized Flex program ALWAYS executes
# its generated Python in a Deno/Pyodide WASM sandbox (dspy.PythonInterpreter
# shells out to `deno` on PATH) — even the un-optimized baseline runs through
# the interpreter — so the runtime image needs the deno binary plus a warm
# npm:pyodide cache (~40MB binary + ~14MB pyodide).
# DENO_DIR must match at build and run time so the runtime sandbox hits the
# cache primed here; it lives under /app so the chgrp/chmod below makes it
# group-0 writable for the runtime v8 code cache. Air-gap: point
# DENO_DOWNLOAD_BASE (binary) and NPM_CONFIG_REGISTRY (pyodide wheel) inside
# and `deno cache` fetches nothing public.
ARG DENO_VERSION=2.6.6
ARG DENO_DOWNLOAD_BASE=https://github.com/denoland/deno/releases/download
ARG NPM_CONFIG_REGISTRY
ENV DENO_DIR=/app/.deno
RUN case "$(dpkg --print-architecture)" in \
        amd64) DENO_TARGET=x86_64-unknown-linux-gnu ;; \
        arm64) DENO_TARGET=aarch64-unknown-linux-gnu ;; \
        *) echo "unsupported arch for Deno: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac \
    && curl -fsSL --retry 3 "$DENO_DOWNLOAD_BASE/v$DENO_VERSION/deno-$DENO_TARGET.zip" -o /tmp/deno.zip \
    && unzip -o /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && chmod +x /usr/local/bin/deno \
    && if [ "$PKG_MANAGER" = "uv" ]; then PY=/app/.venv/bin/python; else PY=python; fi \
    && RUNNER_JS=$("$PY" -c 'import os, dspy.primitives.python_interpreter as m; print(os.path.join(os.path.dirname(m.__file__), "runner.js"))') \
    && ${NPM_CONFIG_REGISTRY:+NPM_CONFIG_REGISTRY=$NPM_CONFIG_REGISTRY} deno cache "$RUNNER_JS"

COPY . .

# Install the project itself. pip does an editable --no-deps install (every
# dependency is already present from the layer above); uv re-syncs now that the
# project source is in place.
RUN if [ "$PKG_MANAGER" = "pip" ]; then \
        pip install --no-cache-dir --no-deps \
            ${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL} \
            ${PIP_TRUSTED_HOST:+--trusted-host $PIP_TRUSTED_HOST} \
            -e .; \
    else \
        UV_PYTHON_DOWNLOADS=never uv sync --frozen; \
    fi

ARG GIT_SHA=unknown

# Use UID 1001 with GID 0 — works everywhere (Docker, Podman, OpenShift restricted-v2 SCC).
# OpenShift assigns a random UID at runtime but always with GID 0, so /app must be
# group-0-owned and group-writable for the editable install metadata to be accessible.
RUN groupadd -g 1001 appuser 2>/dev/null || true \
    && useradd -u 1001 -g 0 -m -s /sbin/nologin appuser \
    && chgrp -R 0 /app \
    && chmod -R g=u /app

USER 1001

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV WORKER_CONCURRENCY=2
ENV WORKER_POLL_INTERVAL=2.0
ENV SKYNET_CODE_VERSION=$GIT_SHA
ENV LOG_LEVEL=INFO
# Containerized runs default to structured logs; override to "text" only
# when running the image interactively for debugging.
ENV LOG_FORMAT=json
# air-gap — litellm uses its bundled cost map instead of fetching model_prices_and_context_window.json from GitHub on import.
ENV LITELLM_LOCAL_MODEL_COST_MAP=True
# REMOTE_DB_URL must be set at runtime (e.g., via docker-compose or -e flag)
# ENV REMOTE_DB_URL=postgresql://user:password@host:5432/skynet

EXPOSE 8000

# One image, two roles: the API (default) and the standalone job worker
# (SERVICE_ROLE=worker, no HTTP). Railway deploys both services from this
# same Dockerfile; the env var picks the entrypoint so neither service needs
# a dashboard-only custom start command.
# Bind the platform-provided PORT when present (Railway/Heroku-style runtimes
# inject it and route edge traffic to it) so the bound port always matches
# settings.port and the generalist agent's derived MCP self-dial URL. The
# sh -c + exec keeps the process as PID 1 for clean SIGTERM handling.
CMD ["sh", "-c", "if [ \"$SERVICE_ROLE\" = \"worker\" ]; then exec python worker_main.py; else exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}; fi"]
