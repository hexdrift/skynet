# Air-Gap Deployment Guide

This is the operator path for moving Skynet into an internet-isolated
environment when you already have the required internal mirrors, images,
secrets, IdP, LLM gateway, CA bundle, and Postgres available.

## Migration Plan

The flow assumes you cloned the repo onto a host inside the air gap and
have an internal Artifactory + OpenShift cluster ready. Each step has a
matching `scripts/airgap_migrate.sh` command — none of them need internet.

| # | Step | Command |
|---|------|---------|
| 1 | Clone the repo + `git lfs pull` (vendored embedder weights) | `git lfs install && git lfs pull` |
| 2 | List every URL/secret/CIDR you must change | `scripts/airgap_migrate.sh todos` |
| 3 | Edit the lines emitted in step 2 (LLM gateway, ADFS issuer, DB, CIDRs) | (editor) |
| 4 | Verify lockfiles, vendored model, alembic dir | `scripts/airgap_migrate.sh check` |
| 5 | Offline alembic dump — review schema delta without touching a DB | `scripts/airgap_migrate.sh validate-migrations` |
| 6 | Build the two Docker images against your internal mirrors | `scripts/airgap_migrate.sh build-images` |
| 7 | Push them to your Artifactory | `scripts/airgap_migrate.sh push-images` |
| 8 | Generate the Helm values file (review the `TODO: On-premise` lines) | `scripts/airgap_migrate.sh values` |
| 9 | Lint + render the chart so you can diff before applying | `scripts/airgap_migrate.sh render` |
| 10 | Install/upgrade — the migration Job runs `alembic upgrade head` first | `scripts/airgap_migrate.sh install` |
| 11 | Smoke test rollout + ADFS callback | `scripts/airgap_migrate.sh status` |

`scripts/airgap_migrate.sh all` runs steps 4, 5, 8, 9, 10, 11 in sequence
once you have your env vars set. Step 2 stays manual because edits don't
script themselves; step 3 is yours.

## Operator Script

```bash
scripts/airgap_migrate.sh configure              # guided values setup
scripts/airgap_migrate.sh todos                  # every TODO marker, in one list
scripts/airgap_migrate.sh check                  # repo artefacts present
scripts/airgap_migrate.sh validate-migrations    # offline alembic --sql, no DB
scripts/airgap_migrate.sh build-images           # docker build BE + FE
scripts/airgap_migrate.sh push-images            # docker push BE + FE
scripts/airgap_migrate.sh values                 # write values-airgap.generated.yaml
scripts/airgap_migrate.sh render                 # helm lint + helm template
scripts/airgap_migrate.sh install                # helm upgrade --install
scripts/airgap_migrate.sh status                 # rollout + smoke commands
scripts/airgap_migrate.sh all                    # check → ... → status
```

Start with `configure` if you want a guided setup. It asks for registry,
image tags, hosts, IdP, database, optional internal CA Secret,
notifications webhook, and egress CIDRs, then writes the Helm values file
and offers to run `check`, `render`, and `install`.

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
OIDC_SCOPE="openid profile email groups" \
AUTH_GROUP_CLAIM=groups \
AUTH_ADMIN_GROUPS=Skynet-Admins \
AUTH_ADMINS=break-glass-admin@example.com \
FRONTEND_HOST=skynet.apps.internal \
BACKEND_HOST=skynet-api.apps.internal \
LLM_EGRESS_CIDR=10.0.5.0/24 \
IDP_EGRESS_CIDR=10.0.6.0/24 \
INTERNAL_CA_SECRET=skynet-internal-ca \
COMMS_WEBHOOK_URL=https://chat.internal/hooks/skynet \
COMMS_EGRESS_CIDR=10.0.7.0/24 \
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
scripts/airgap_migrate.sh validate-migrations
scripts/airgap_migrate.sh todos          # one place to see every URL/secret/CIDR you must change
```

Confirm:

- `backend/vendor/models/jina-code-embeddings-0.5b/model.safetensors`
  is a real file, not a Git LFS pointer.
- `frontend/package-lock.json` is present.
- `backend/uv.lock` is present.
- `backend/alembic/versions/` is present.
- `migration.sql` (from `validate-migrations`) reflects the schema you
  expect.
- Backend, frontend, and pgvector images are available in the internal
  registry you will reference from Helm.
- If your IdP, LLM gateway, Postgres, or webhook uses a private CA, a
  Kubernetes Secret containing the CA bundle is ready.

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

The script wraps the two `docker build` invocations into one command:

```bash
REGISTRY=artifactory.example.com/skynet \
IMAGE_TAG=2026.04.30 \
REGISTRY_PREFIX=artifactory.example.com/docker-remote \
DEBIAN_MIRROR=https://artifactory.example.com/debian-remote \
PIP_INDEX_URL=https://artifactory.example.com/api/pypi/pypi-remote/simple \
PIP_TRUSTED_HOST=artifactory.example.com \
BASE_IMAGE=artifactory.example.com/docker-remote/node:22-alpine \
NPM_REGISTRY=https://artifactory.example.com/api/npm/npm-remote/ \
scripts/airgap_migrate.sh build-images

# Then push:
scripts/airgap_migrate.sh push-images
```

Set `DOCKER=podman` to run on Podman / OpenShift Buildah-compatible
hosts.

The equivalent raw commands (if you prefer to run them directly):

```bash
docker build backend \
  -t artifactory.example.com/skynet/skynet/backend:2026.04.30 \
  --build-arg REGISTRY_PREFIX=artifactory.example.com/docker-remote \
  --build-arg DEBIAN_MIRROR=https://artifactory.example.com/debian-remote \
  --build-arg PIP_INDEX_URL=https://artifactory.example.com/api/pypi/pypi-remote/simple \
  --build-arg PIP_TRUSTED_HOST=artifactory.example.com

docker build frontend \
  -t artifactory.example.com/skynet/skynet/frontend:2026.04.30 \
  --build-arg BASE_IMAGE=artifactory.example.com/docker-remote/node:22-alpine \
  --build-arg NPM_REGISTRY=https://artifactory.example.com/api/npm/npm-remote/

docker push artifactory.example.com/skynet/skynet/backend:2026.04.30
docker push artifactory.example.com/skynet/skynet/frontend:2026.04.30
```

The frontend `package.json` pins `next build --webpack` so the production
build never silently switches to Turbopack. Webpack is reproducible inside
restrictive sandboxes (Turbopack spawns helper processes that bind a local
port and trip restricted-egress / sandboxed CI environments).

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
export BACKEND_AUTH_SECRET="$(openssl rand -base64 32)"

kubectl -n skynet create secret docker-registry artifactory-pull-secret \
  --docker-server=artifactory.example.com \
  --docker-username="$REGISTRY_USER" \
  --docker-password="$REGISTRY_PASSWORD"

kubectl -n skynet create secret generic skynet-db-password \
  --from-literal=password="$POSTGRES_PASSWORD"

kubectl -n skynet create secret generic skynet-backend-secrets \
  --from-literal=OPENAI_API_KEY="$INTERNAL_LLM_API_KEY" \
  --from-literal=BACKEND_AUTH_SECRET="$BACKEND_AUTH_SECRET"

kubectl -n skynet create secret generic skynet-frontend-secrets \
  --from-literal=AUTH_SECRET="$(openssl rand -base64 32)" \
  --from-literal=AUTH_SSO_CLIENT_SECRET="$OIDC_CLIENT_SECRET" \
  --from-literal=BACKEND_AUTH_SECRET="$BACKEND_AUTH_SECRET"

# Only needed when internal endpoints use a private CA.
kubectl -n skynet create secret generic skynet-internal-ca \
  --from-file=ca-bundle.pem=./internal-ca-bundle.pem
```

TODO: On-premise - replace inline `kubectl create secret` commands with
your secret-store flow if you use ExternalSecrets, SealedSecrets, Vault, or
OpenShift GitOps.

---

## Internal ADFS / OIDC Setup

The frontend uses Auth.js/NextAuth with a generic OIDC provider whose id is
`adfs`. In production, configure ADFS and set these frontend env vars through
the generated Helm values and `skynet-frontend-secrets`:

```yaml
frontend:
  env:
    AUTH_SSO_ISSUER: "https://adfs.example.internal/adfs"
    AUTH_SSO_CLIENT_ID: "skynet"
    AUTH_SSO_SCOPE: "openid profile email groups"
    AUTH_GROUP_CLAIM: "groups"
    AUTH_ADMIN_GROUPS: "Skynet-Admins"
    AUTH_ADMINS: "break-glass-admin@example.internal"
  secrets:
    existingSecret: "skynet-frontend-secrets"

backend:
  env:
    ADMIN_GROUPS: "Skynet-Admins"
    ADMIN_USERNAMES: "break-glass-admin@example.internal"
  secrets:
    existingSecret: "skynet-backend-secrets"
```

The Secret must contain:

```text
AUTH_SECRET
AUTH_SSO_CLIENT_SECRET
BACKEND_AUTH_SECRET
```

`BACKEND_AUTH_SECRET` must be the same value in the backend and frontend
Secrets. The frontend signs short-lived backend bearer tokens with it, and the
backend verifies the signature, issuer, audience, and expiry before allowing
admin API calls.

Register Skynet in ADFS as an OpenID Connect web application:

- Redirect URI:
  `https://<frontend-host>/api/auth/callback/adfs`
- Issuer:
  `https://<adfs-host>/adfs`
- Client authentication:
  confidential client with client secret
- Scopes:
  `openid profile email groups` if your ADFS release supports group scope.
- Claims:
  include at least one stable user identifier. The app accepts `name`,
  `unique_name`, `upn`, `preferred_username`, `email`, or `sub`.
- Groups:
  emit the admin group in the claim named by `AUTH_GROUP_CLAIM` (default
  `groups`). Put that same group name in frontend `AUTH_ADMIN_GROUPS` and
  backend `ADMIN_GROUPS`. Use `AUTH_ADMINS` / `ADMIN_USERNAMES` only as a
  break-glass path for named operators.

For the default generated host, the callback is:

```text
https://skynet.apps.internal/api/auth/callback/adfs
```

If ADFS uses an internal/private CA, create `skynet-internal-ca` and set
`INTERNAL_CA_SECRET` when generating values. This mounts the CA and sets
`NODE_EXTRA_CA_CERTS`, which is required for the server-side OIDC discovery
request to `/.well-known/openid-configuration`.

TODO: On-premise - confirm the exact ADFS issuer URL. Some ADFS deployments
publish OIDC metadata at `https://host/adfs/.well-known/openid-configuration`;
the issuer value should be the issuer advertised by that metadata document,
usually `https://host/adfs`.

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

### Offline schema review (no DB required)

Before pushing the backend image, you can dump the exact SQL the in-cluster
migration Job will execute. This is the path to use when your build host
has no Postgres reachable (e.g., sandboxed CI):

```bash
scripts/airgap_migrate.sh validate-migrations
# wrote offline migration SQL: ./migration.sql
```

Under the hood this calls `alembic upgrade head --sql` against the same
`alembic/env.py` the Job uses, so the offline output is byte-for-byte the
DDL the cluster will run. Review `./migration.sql`, then proceed to
`build-images` / `install`.

### In-cluster migration Job

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

## Private TLS / CA Bundles

If internal endpoints use a private CA, set `INTERNAL_CA_SECRET` while
running `scripts/airgap_migrate.sh configure` or `values`. The generated
values file will:

- mount the CA Secret into backend and frontend pods,
- set `NODE_EXTRA_CA_CERTS` for NextAuth/OIDC in the frontend,
- set `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` for Python HTTP clients in
  the backend and migration Job.

Example:

```bash
INTERNAL_CA_SECRET=skynet-internal-ca \
INTERNAL_CA_FILENAME=ca-bundle.pem \
scripts/airgap_migrate.sh values
```

TODO: On-premise - confirm whether your internal LLM gateway uses a public
or private CA. If private, include the CA Secret in your release runbook.

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

## Live User Quotas

The default optimization cap is `MAX_JOBS_PER_USER=100`. Static env values
still work for broad defaults:

- `QUOTA_OVERRIDES`: JSON map such as `{"power@example.com": 500}` or
  `{"researcher@example.com": null}`.

For day-to-day changes, use the admin tab in the settings modal. Admins can
set a numeric quota, set a user to unlimited, or remove a live override so the
user falls back to the default/static config.

Deploy the migration once so `user_quota_overrides` and
`user_quota_audit_events` exist. After that, backend quota enforcement reads
the override table on each submission/clone/retry, so updates take effect
immediately without a backend restart. The admin tab also shows the latest
quota audit events.

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

## Remaining Operator Responsibilities

The repo cannot automate these site-specific pieces:

- Mirroring/pushing images and package repositories into your internal
  Artifactory/registry.
- Creating Kubernetes Secrets and rotating credentials.
- Supplying exact NetworkPolicy CIDRs for IdP, LLM gateway, webhook, and DB.
- Backing up and restoring Postgres.
- Choosing internal model IDs exposed by your LLM gateway. The generated
  values default `CODE_AGENT_MODEL` and `GENERALIST_AGENT_MODEL` to `gpt-5`;
  change them if your gateway exposes different names.
- Deciding whether to enable recommendations. The app runs without
  `sentence-transformers`; recommendations degrade to an empty/no-op
  feature unless the backend image includes the `[recommendations]` extra.

---

## Audit TODOs

Run this regularly:

```bash
scripts/airgap_migrate.sh todos
# or, equivalently:
git grep -n "TODO: On-premise\|TODO: On-prem"
```

Current intentional TODO locations:

- `AIRGAP.md` — context for each on-prem decision.
- `deploy/helm/skynet/values-airgap.generated.yaml` — after `values`.
- `scripts/airgap_migrate.sh` — defaults emitted into the values file.
- `frontend/.env.example` — frontend dev/runtime env template.
- `frontend/.npmrc` — internal npm registry mirror config (commented out).
- `backend/core/config.py` — model id, agent base URLs, embedder path.

If new external services are added, add them to this file, the Helm values,
and `scripts/airgap_migrate.sh`. Then `todos` will pick them up
automatically.
