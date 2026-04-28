# On-Prem Deployment Checklist

Single source of truth for the placeholders an operator must replace before
deploying Skynet inside an air-gapped or mirror-only environment. The
defaults in `Dockerfile`, `pyproject.toml`, `package.json`, and the Helm
chart all assume the public registries; everything below points at the
internal mirror equivalents.

Replace `artifactory.your-company.com` with your actual artifactory host
throughout.

---

## 1. Container base images

| File | Default | Replace with |
|------|---------|--------------|
| `backend/Dockerfile`  | `FROM python:3.11-slim`   | `FROM artifactory.your-company.com/docker-remote/python:3.11-slim` |
| `frontend/Dockerfile` | `FROM node:22-alpine AS base` | `FROM artifactory.your-company.com/docker-remote/node:22-alpine AS base` |

Or — preferred — pre-bake an internal `skynet/python-base` and
`skynet/node-base` image in your registry and swap the `FROM` line to that.

## 2. apt mirror (backend image only)

`backend/Dockerfile` runs `apt-get update && apt-get install` for
`build-essential` and `curl`. In a locked-down build environment, repoint
apt before that line:

```dockerfile
RUN echo "deb https://artifactory.your-company.com/debian-remote bookworm main" \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/*
```

Or pre-bake the two packages into your custom Python base image so
`apt-get` is never invoked at build time.

## 3. pip index (backend)

Two equivalent ways to repoint pip — pick whichever your build pipeline
prefers:

**Option A — `pip.conf` baked into the image** (`backend/Dockerfile`,
before `RUN pip install -e .`):

```dockerfile
RUN pip config set global.index-url \
      https://artifactory.your-company.com/api/pypi/pypi-remote/simple \
    && pip config set global.trusted-host artifactory.your-company.com
```

**Option B — flags on the install line**:

```dockerfile
RUN pip install -e . \
      --index-url https://artifactory.your-company.com/api/pypi/pypi-remote/simple \
      --trusted-host artifactory.your-company.com
```

`backend/pyproject.toml` does NOT need editing — pip configuration is
runtime/build-time, not project-level.

## 4. npm registry (frontend)

`frontend/.npmrc` already exists as the wiring point. Populate it before
running `docker build`:

```
registry=https://artifactory.your-company.com/api/npm/npm-remote/
//artifactory.your-company.com/api/npm/npm-remote/:_authToken=${NPM_TOKEN}
always-auth=true
```

Pass `NPM_TOKEN` via build arg or CI secret. `frontend/Dockerfile`
already copies `.npmrc*` into the deps stage, so no Dockerfile edit is
required once the file is populated.

## 5. Helm chart image registry

`deploy/helm/skynet/values.yaml` exposes a global registry prefix:

```yaml
global:
  imageRegistry: artifactory.your-company.com/skynet
  imagePullSecrets:
    - name: artifactory-pull-secret
```

When set, every image (`backend`, `frontend`, `pgvector/pgvector`) is
prefixed with that registry. Create the `artifactory-pull-secret`
docker-registry Secret in the target namespace before `helm install`.

## 6. LLM gateway (optional)

If your environment cannot reach `api.openai.com` / `api.anthropic.com` /
`api.fireworks.ai` directly, point the backend at an internal LLM
gateway via:

```yaml
backend:
  env:
    CODE_AGENT_BASE_URL: https://llm-gateway.internal/v1
    CODE_AGENT_MODEL: gpt-5
    GENERALIST_AGENT_BASE_URL: https://llm-gateway.internal/v1
    GENERALIST_AGENT_MODEL: gpt-5
```

And lock down egress:

```yaml
networkPolicy:
  llmEgress:
    - cidr: 10.0.5.0/24      # internal LLM gateway subnet
      ports: [443]
```

See `deploy/helm/skynet/values.yaml` (`networkPolicy.llmEgress`) for
the full schema.

## 7. TLS certificates (OpenShift Route)

By default the chart uses the OpenShift router's wildcard cert. To
serve a custom certificate:

```bash
helm install skynet ./deploy/helm/skynet \
  --set-file openshift.routes.frontend.tls.certificate=./tls/frontend.crt \
  --set-file openshift.routes.frontend.tls.key=./tls/frontend.key \
  --set-file openshift.routes.frontend.tls.caCertificate=./tls/ca-bundle.crt
```

For `reencrypt` termination, also pass
`openshift.routes.frontend.tls.destinationCACertificate`.

## 8. Database

For production, point at a managed pgvector cluster (Crunchy,
CloudNativePG, RDS, etc.) instead of the bundled single-replica
StatefulSet:

```yaml
externalDatabase:
  enabled: true
  host: pgvector.internal
  port: 5432
  database: skynet
  user: skynet
  existingSecret: skynet-db-password
  existingSecretKey: password
  sslmode: require

postgres:
  enabled: false
```

If you keep the bundled Postgres, schedule PVC snapshots externally
(Velero, CSI VolumeSnapshot, or your cluster backup operator). The
chart does NOT take backups for you.

---

## Quick-start: minimum on-prem overrides

A single `values-onprem.yaml` covering the common case:

```yaml
global:
  imageRegistry: artifactory.your-company.com/skynet
  imagePullSecrets:
    - name: artifactory-pull-secret

backend:
  env:
    CODE_AGENT_BASE_URL: https://llm-gateway.internal/v1
    CODE_AGENT_MODEL: gpt-5
    GENERALIST_AGENT_BASE_URL: https://llm-gateway.internal/v1
    GENERALIST_AGENT_MODEL: gpt-5

externalDatabase:
  enabled: true
  host: pgvector.internal
  existingSecret: skynet-db-password

postgres:
  enabled: false

networkPolicy:
  llmEgress:
    - cidr: 10.0.5.0/24
      ports: [443]
```

Install:

```bash
helm install skynet ./deploy/helm/skynet -f values-onprem.yaml
```

---

## Frontend runtime-env smoke test

The frontend image is built once and points at any backend at runtime,
because `API_URL` (and `APP_VERSION`) are read inside the Next.js server
component on every request and serialized into a `<script>` tag that
sets `window.__SKYNET_ENV__` before hydration. See
`frontend/src/shared/lib/runtime-env.ts` for the implementation.

**This means: changing `API_URL` should take effect on the next pod
restart, with no rebuild.** If it doesn't, runtime-env is broken.

Verification steps once you've installed the chart:

### 1. Inspect the injected script from inside the pod

```bash
oc exec -n <ns> deploy/<release>-skynet-frontend -- \
  curl -sf http://localhost:3001/ \
  | grep -o 'window.__SKYNET_ENV__=[^<]*' \
  | head -c 500
```

You should see something like:

```
window.__SKYNET_ENV__=JSON.parse("{\"apiUrl\":\"http://<release>-skynet-backend:8000\",\"appVersion\":\"0.1.0\"}");
```

The `apiUrl` value must match `frontend.env.API_URL` from values.yaml
(or the auto-default `http://<release>-skynet-backend:8000` if API_URL
is empty).

### 2. Inspect from outside the cluster (via Route)

```bash
curl -sf https://<frontend-route> \
  | grep -o 'window.__SKYNET_ENV__=[^<]*' \
  | head -c 500
```

Same expectation. If the Route uses TLS edge with the router's default
cert, pass `-k` if your local trust store doesn't have the router CA.

### 3. Flip API_URL and confirm it changes

```bash
helm upgrade skynet ./deploy/helm/skynet --reuse-values \
  --set frontend.env.API_URL=https://staging-backend.example.com

# wait for rollout
oc rollout status deploy/<release>-skynet-frontend -n <ns>

# re-inspect — apiUrl should now be staging-backend.example.com
oc exec -n <ns> deploy/<release>-skynet-frontend -- \
  curl -sf http://localhost:3001/ \
  | grep -o 'window.__SKYNET_ENV__=[^<]*' \
  | head -c 500
```

If the value didn't change, runtime-env is being short-circuited
somewhere — most likely the build inlined `NEXT_PUBLIC_API_URL` and is
winning over the runtime override. Check `frontend/.env*` files and
the build args.

### 4. Browser-side check

Open the frontend Route in a browser, open DevTools → Console, run:

```js
window.__SKYNET_ENV__
```

Should print `{ apiUrl: "...", appVersion: "..." }`. Then in the
Network tab, trigger any API action (e.g. open the dashboard) and
confirm the requests go to `apiUrl`, not to `localhost:8000` or any
build-time default.

### Common failure modes

| Symptom | Likely cause |
|---------|--------------|
| `window.__SKYNET_ENV__` is `undefined` in the browser | The injected `<script>` was stripped (CSP? proxy that rewrites HTML?). Inspect raw HTML from `curl`. |
| `apiUrl` is `http://localhost:8000` despite setting `API_URL` | `process.env.API_URL` is not visible to the Node runtime. Check `oc exec ... -- env \| grep API_URL`. |
| `apiUrl` is the old value after `helm upgrade` | Pod wasn't restarted. The frontend reads `process.env` at request time, but Node caches resolved values per-process — restart with `oc rollout restart`. |
| Network requests still hit the wrong host | A client-side feature flag or hardcoded URL is bypassing `getRuntimeEnv()`. Grep `frontend/src` for `localhost:8000` or hardcoded backend URLs. |
