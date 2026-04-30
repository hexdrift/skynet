# Air-Gap Deployment Guide

This is the operator path for moving Skynet into an internet-isolated
environment when you already have the required internal mirrors, images,
secrets, IdP, LLM gateway, and Postgres available.

The goal is to make migration boring:

1. Build or import images into your internal registry.
2. Generate a reviewed Helm values file.
3. Let the Helm migration hook run `alembic upgrade head`.
4. Smoke test without any public internet egress.

## Operator Script

The repo includes a migration helper:

```bash
scripts/airgap_migrate.sh configure
scripts/airgap_migrate.sh check
scripts/airgap_migrate.sh values
scripts/airgap_migrate.sh render
scripts/airgap_migrate.sh install
scripts/airgap_migrate.sh status
```

Start with `configure` if you want a guided setup. It asks for registry,
image tags, hosts, IdP, database, and egress CIDRs, then writes the Helm
values file and offers to run `check`, `render`, and `install`.

Most installs should use environment overrides instead of editing the
script:

```bash
RELEASE=skynet \
NAMESPACE=skynet \
REGISTRY=artifactory.example.com/skynet \
IMAGE_TAG=2026.04.30 \
PULL_SECRET=artifactory-pull-secret \
EXTERNAL_DB_HOST=pgvector.internal \
EXTERNAL_DB_SECRET=skynet-db-password \
LLM_BASE_URL=https://llm-gateway.internal/v1 \
OIDC_ISSUER=https://idp.internal/realms/skynet \
OIDC_CLIENT_ID=skynet \
FRONTEND_HOST=skynet.apps.internal \
BACKEND_HOST=skynet-api.apps.internal \
LLM_EGRESS_CIDR=10.0.5.0/24 \
IDP_EGRESS_CIDR=10.0.6.0/24 \
scripts/airgap_migrate.sh all
```

`values` writes:

```text
deploy/helm/skynet/values-airgap.generated.yaml
```

That generated file intentionally contains `TODO: On-premise` comments.
Review them before `install`.

---

## Pre-Transfer Checklist

Run this before moving the repo or release bundle into the air gap:

```bash
git lfs install
git lfs pull
scripts/airgap_migrate.sh check
```

Confirm:

- `backend/vendor/models/jina-code-embeddings-0.5b/model.safetensors`
  is a real file, not a Git LFS pointer.
- `frontend/package-lock.json` is present.
- `backend/uv.lock` is present.
- `backend/alembic/versions/` is present.
- Backend, frontend, and pgvector images are available in the internal
  registry you will reference from Helm.

Recommended release bundle contents:

- Git checkout or source archive.
- `backend` image tar or internal registry image.
- `frontend` image tar or internal registry image.
- `pgvector/pgvector:pg16` mirror, unless using an external managed DB.
- Helm chart under `deploy/helm/skynet`.
- Secrets material handled by your secret-management process, not committed
  into the bundle.

---

## Build Images Against Internal Mirrors

Replace `artifactory.example.com` with your actual registry host. The
examples assume your registry exposes Docker Hub, Debian, PyPI, and npm
mirrors.

Backend:

```bash
docker build backend \
  -t artifactory.example.com/skynet/skynet/backend:2026.04.30 \
  --build-arg REGISTRY_PREFIX=artifactory.example.com/docker-remote \
  --build-arg DEBIAN_MIRROR=https://artifactory.example.com/debian-remote \
  --build-arg PIP_INDEX_URL=https://artifactory.example.com/api/pypi/pypi-remote/simple \
  --build-arg PIP_TRUSTED_HOST=artifactory.example.com
```

Frontend:

```bash
docker build frontend \
  -t artifactory.example.com/skynet/skynet/frontend:2026.04.30 \
  --build-arg BASE_IMAGE=artifactory.example.com/docker-remote/node:22-alpine \
  --build-arg NPM_REGISTRY=https://artifactory.example.com/api/npm/npm-remote/
```

Push or import the images according to your registry process:

```bash
docker push artifactory.example.com/skynet/skynet/backend:2026.04.30
docker push artifactory.example.com/skynet/skynet/frontend:2026.04.30
```

TODO: On-premise - if your registry does not expose Docker Hub mirrors as
`docker-remote/python`, `docker-remote/node`, and `pgvector/pgvector`,
document the exact internal image names in your site runbook.

Mirror notes:

- Container base images: pass `REGISTRY_PREFIX` for backend and
  `BASE_IMAGE` for frontend. You can also pre-bake internal
  `skynet/python-base` and `skynet/node-base` images.
- Debian packages: pass `DEBIAN_MIRROR`, or pre-bake `build-essential` and
  `curl` into the Python base image.
- Python packages: pass `PIP_INDEX_URL` and `PIP_TRUSTED_HOST`.
- npm packages: pass `NPM_REGISTRY`; the Dockerfile sets
  `replace-registry-host=always` so lockfile tarball hosts are rewritten to
  the mirror.
- Helm images: set `global.imageRegistry` and `global.imagePullSecrets` in
  the generated values file. That prefixes backend, frontend, and
  `pgvector/pgvector` images.

---

## Required Kubernetes Secrets

Create these before running the Helm install. Names match the generated
values file; change them there if your platform uses different names.

```bash
kubectl -n skynet create secret docker-registry artifactory-pull-secret \
  --docker-server=artifactory.example.com \
  --docker-username="$REGISTRY_USER" \
  --docker-password="$REGISTRY_PASSWORD"

kubectl -n skynet create secret generic skynet-db-password \
  --from-literal=password="$POSTGRES_PASSWORD"

kubectl -n skynet create secret generic skynet-backend-secrets \
  --from-literal=OPENAI_API_KEY="$INTERNAL_LLM_API_KEY"

kubectl -n skynet create secret generic skynet-frontend-secrets \
  --from-literal=AUTH_SECRET="$(openssl rand -base64 32)" \
  --from-literal=AUTH_SSO_CLIENT_SECRET="$OIDC_CLIENT_SECRET"
```

TODO: On-premise - replace inline `kubectl create secret` commands with
your secret-store flow if you use ExternalSecrets, SealedSecrets, Vault, or
OpenShift GitOps.

---

## TLS Certificates

By default the chart uses the OpenShift router's wildcard certificate. To
serve a custom certificate:

```bash
helm upgrade --install skynet deploy/helm/skynet \
  -n skynet --create-namespace \
  -f deploy/helm/skynet/values-airgap.generated.yaml \
  --set-file openshift.routes.frontend.tls.certificate=./tls/frontend.crt \
  --set-file openshift.routes.frontend.tls.key=./tls/frontend.key \
  --set-file openshift.routes.frontend.tls.caCertificate=./tls/ca-bundle.crt
```

For `reencrypt` termination, also set
`openshift.routes.frontend.tls.destinationCACertificate`.

---

## Database Migration

The Helm chart runs a pre-install/pre-upgrade Job:

```yaml
migration:
  enabled: true
  command: ["alembic", "upgrade", "head"]
```

The migration Job uses the same backend image and the same `REMOTE_DB_URL`
composition as backend pods. Helm waits for the Job to succeed before
starting new backend pods.

First install or upgrade:

```bash
scripts/airgap_migrate.sh install
```

Check migration logs:

```bash
kubectl -n skynet logs job/skynet-skynet-migrate
```

If you are adopting a database that already has the baseline schema created
outside Alembic, do a one-time stamp instead:

```bash
helm upgrade --install skynet deploy/helm/skynet \
  -n skynet --create-namespace \
  -f deploy/helm/skynet/values-airgap.generated.yaml \
  --set-json 'migration.command=["alembic","stamp","0001"]'
```

Then revert to `["alembic", "upgrade", "head"]` for the next upgrade.

TODO: On-premise - capture your DB backup/restore process and RPO/RTO. The
chart does not take Postgres backups for you.

---

## Runtime Egress

Known intended runtime egress:

- Frontend to internal OIDC issuer.
- Backend to internal LLM gateway.
- Backend and frontend to Postgres only through the cluster/service network
  or managed DB endpoint.
- Optional notifications webhook if configured.

Known risky endpoint by design:

- `POST /models/discover` accepts a user-supplied `base_url` so operators
  can discover models from an internal OpenAI-compatible gateway. In an
  air gap, enforce egress with NetworkPolicy/firewall rules.

The generated values file sets `networkPolicy.egressCidrs` and
`networkPolicy.llmEgress` to placeholders. Tighten those to exact internal
CIDRs.

TODO: On-premise - record the exact CIDRs for IdP, LLM gateway, notification
webhook, and managed Postgres in your environment-specific values file.

---

## Smoke Test

After install:

```bash
kubectl -n skynet rollout status deploy/skynet-skynet-backend
kubectl -n skynet rollout status deploy/skynet-skynet-frontend

curl -k https://skynet.apps.internal/
curl -k https://skynet-api.apps.internal/health
```

From the UI:

- Sign in through SSO.
- Submit a tiny optimization.
- Confirm worker logs show the job moving through validation, dataset split,
  optimization, and final evaluation.
- Confirm no pod attempts DNS resolution for public hosts.

Runtime-env check:

```bash
kubectl -n skynet exec deploy/skynet-skynet-frontend -- \
  curl -sf http://localhost:3001/ \
  | grep -o 'window.__SKYNET_ENV__=[^<]*' \
  | head -c 500
```

The `apiUrl` should match `frontend.env.API_URL` in the generated values
file. Changing `API_URL` should take effect after a frontend pod restart
without rebuilding the image.

---

## What Is Already Air-Gap Clean

- Scalar API docs are vendored under `backend/core/api/static/scalar/`.
- Fonts are bundled through npm packages, not Google Fonts.
- The recommendations embedder is vendored under `backend/vendor/models/`.
- Sentry is gated so builds without a DSN do not ship it.
- LiteLLM telemetry is disabled in backend configuration.
- Storage is Postgres; there is no S3/GCS/Azure Blob dependency.
- Auth is Credentials plus generic OIDC; no Google/GitHub OAuth provider is
  configured.

---

## Audit TODOs

Run this regularly:

```bash
git grep -n "TODO: On-premise"
```

Current intentional TODO locations:

- `AIRGAP.md`
- `deploy/helm/skynet/values-airgap.generated.yaml` after generation
- `frontend/.env.example`

If new external services are added, add them to this file, the Helm values,
and `scripts/airgap_migrate.sh`.
