#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART_DIR="$ROOT_DIR/deploy/helm/skynet"

RELEASE="${RELEASE:-skynet}"
NAMESPACE="${NAMESPACE:-skynet}"
VALUES_OUT="${VALUES_OUT:-$ROOT_DIR/deploy/helm/skynet/values-airgap.generated.yaml}"
REGISTRY="${REGISTRY:-artifactory.your-company.com/skynet}"
IMAGE_TAG="${IMAGE_TAG:-0.1.0}"
PULL_SECRET="${PULL_SECRET:-artifactory-pull-secret}"
BACKEND_REPOSITORY="${BACKEND_REPOSITORY:-skynet/backend}"
FRONTEND_REPOSITORY="${FRONTEND_REPOSITORY:-skynet/frontend}"
POSTGRES_REPOSITORY="${POSTGRES_REPOSITORY:-pgvector/pgvector}"
EXTERNAL_DB_HOST="${EXTERNAL_DB_HOST:-pgvector.internal}"
EXTERNAL_DB_SECRET="${EXTERNAL_DB_SECRET:-skynet-db-password}"
BACKEND_SECRET="${BACKEND_SECRET:-skynet-backend-secrets}"
FRONTEND_SECRET="${FRONTEND_SECRET:-skynet-frontend-secrets}"
INTERNAL_CA_SECRET="${INTERNAL_CA_SECRET:-}"
INTERNAL_CA_FILENAME="${INTERNAL_CA_FILENAME:-ca-bundle.pem}"
INTERNAL_CA_MOUNT_DIR="${INTERNAL_CA_MOUNT_DIR:-/etc/skynet/ca}"
LLM_BASE_URL="${LLM_BASE_URL:-https://llm-gateway.internal/v1}"
OIDC_ISSUER="${OIDC_ISSUER:-https://idp.internal/realms/skynet}"
OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-skynet}"
OIDC_SCOPE="${OIDC_SCOPE:-openid profile email groups}"
AUTH_GROUP_CLAIM="${AUTH_GROUP_CLAIM:-groups}"
AUTH_ADMIN_GROUPS="${AUTH_ADMIN_GROUPS:-}"
AUTH_ADMINS="${AUTH_ADMINS:-}"
FRONTEND_HOST="${FRONTEND_HOST:-skynet.apps.internal}"
BACKEND_HOST="${BACKEND_HOST:-skynet-api.apps.internal}"
LLM_EGRESS_CIDR="${LLM_EGRESS_CIDR:-10.0.5.0/24}"
IDP_EGRESS_CIDR="${IDP_EGRESS_CIDR:-10.0.6.0/24}"
COMMS_WEBHOOK_URL="${COMMS_WEBHOOK_URL:-}"
COMMS_EGRESS_CIDR="${COMMS_EGRESS_CIDR:-}"

usage() {
  cat <<'EOF'
Usage: scripts/airgap_migrate.sh <command>

Migration plan (matches AIRGAP.md):
  1. clone repo on the air-gapped host
  2. `todos`               list every TODO marker the operator must change
  3. edit URLs/secrets/CIDRs in those files
  4. `check`               verify lockfiles, vendored model, alembic dir present
  5. `validate-migrations` offline alembic --sql dump (no DB required)
  6. `build-images`        docker build backend + frontend against internal mirrors
  7. `push-images`         docker push to internal Artifactory
  8. `values` + `render`   generate + lint Helm values file
  9. `install`             helm upgrade --install (runs migration Job first)
  10. `status`             rollout + smoke-test commands

Commands:
  configure            Prompt for on-prem values, write values file, optionally render/install.
  todos                Print every TODO: On-premise marker the operator must edit.
  check                Verify local repo artifacts needed for an air-gapped rollout.
  validate-migrations  Run `alembic upgrade head --sql` offline (no DB) to review schema.
  build-images         docker build backend + frontend with internal mirror build args.
  push-images          docker push backend + frontend tags to the internal registry.
  values               Generate deploy/helm/skynet/values-airgap.generated.yaml.
  render               Run helm lint + helm template with the generated values.
  install              Run helm upgrade --install; the Helm migration hook runs first.
  status               Print rollout status commands for backend/frontend.
  all                  Run check, validate-migrations, values, render, install, status.

Common environment overrides:
  RELEASE=skynet
  NAMESPACE=skynet
  REGISTRY=artifactory.example.com/skynet
  IMAGE_TAG=2026.04.30
  PULL_SECRET=artifactory-pull-secret
  EXTERNAL_DB_HOST=pgvector.internal
  EXTERNAL_DB_SECRET=skynet-db-password
  BACKEND_SECRET=skynet-backend-secrets
  FRONTEND_SECRET=skynet-frontend-secrets
  INTERNAL_CA_SECRET=skynet-internal-ca
  LLM_BASE_URL=https://llm-gateway.internal/v1
  OIDC_ISSUER=https://idp.internal/realms/skynet
  OIDC_CLIENT_ID=skynet
  OIDC_SCOPE="openid profile email groups"
  AUTH_GROUP_CLAIM=groups
  AUTH_ADMIN_GROUPS=Skynet-Admins
  AUTH_ADMINS=break-glass-admin@example.com
  FRONTEND_HOST=skynet.apps.internal
  BACKEND_HOST=skynet-api.apps.internal
  LLM_EGRESS_CIDR=10.0.5.0/24
  IDP_EGRESS_CIDR=10.0.6.0/24
  COMMS_WEBHOOK_URL=https://chat.internal/hooks/skynet
  COMMS_EGRESS_CIDR=10.0.7.0/24

Image build / push overrides (build-images, push-images):
  DOCKER=docker                                # or `podman`
  REGISTRY_PREFIX=artifactory.example.com/docker-remote
  DEBIAN_MIRROR=https://artifactory.example.com/debian-remote
  PIP_INDEX_URL=https://artifactory.example.com/api/pypi/pypi-remote/simple
  PIP_TRUSTED_HOST=artifactory.example.com
  BASE_IMAGE=artifactory.example.com/docker-remote/node:22-alpine
  NPM_REGISTRY=https://artifactory.example.com/api/npm/npm-remote/

Assumptions:
  - backend/frontend/postgres images already exist in the internal registry,
    or you ran `build-images` + `push-images` against your Artifactory.
  - the namespace already has image pull, DB password, AUTH_SECRET,
    BACKEND_AUTH_SECRET, and OIDC client-secret Kubernetes secrets.
  - kubectl or oc is already authenticated to the target cluster.
EOF
}

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

prompt() {
  local var_name="$1"
  local label="$2"
  local current="${!var_name}"
  local answer
  read -r -p "$label [$current]: " answer
  if [[ -n "$answer" ]]; then
    printf -v "$var_name" '%s' "$answer"
  fi
}

prompt_secret_name() {
  local var_name="$1"
  local label="$2"
  local current="${!var_name}"
  local answer
  read -r -p "$label [$current]: " answer
  if [[ -n "$answer" ]]; then
    printf -v "$var_name" '%s' "$answer"
  fi
}

confirm() {
  local label="$1"
  local answer
  read -r -p "$label [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" || "$answer" == "YES" ]]
}

cmd_configure() {
  if [[ ! -t 0 ]]; then
    echo "configure requires an interactive terminal" >&2
    exit 1
  fi

  cat <<'EOF'
Skynet air-gap setup

Press Enter to accept a default. Secrets are referenced by Kubernetes Secret
name only; this script does not ask for secret values or write credentials.
EOF

  prompt RELEASE "Helm release name"
  prompt NAMESPACE "Kubernetes namespace"
  prompt VALUES_OUT "Output values file"
  prompt REGISTRY "Internal image registry prefix"
  prompt IMAGE_TAG "Backend/frontend image tag"
  prompt PULL_SECRET "Image pull secret name"
  prompt BACKEND_REPOSITORY "Backend image repository under registry"
  prompt FRONTEND_REPOSITORY "Frontend image repository under registry"
  prompt POSTGRES_REPOSITORY "pgvector image repository under registry"
  prompt EXTERNAL_DB_HOST "External pgvector host"
  prompt_secret_name EXTERNAL_DB_SECRET "DB password Secret name"
  prompt_secret_name BACKEND_SECRET "Backend Secret name"
  prompt_secret_name FRONTEND_SECRET "Frontend Secret name"
  prompt_secret_name INTERNAL_CA_SECRET "Internal CA Secret name (blank to skip)"
  if [[ -n "$INTERNAL_CA_SECRET" ]]; then
    prompt INTERNAL_CA_FILENAME "Internal CA filename in Secret"
    prompt INTERNAL_CA_MOUNT_DIR "Internal CA mount directory"
  fi
  prompt LLM_BASE_URL "Internal OpenAI-compatible LLM base URL"
  prompt OIDC_ISSUER "Internal ADFS/OIDC issuer URL"
  prompt OIDC_CLIENT_ID "ADFS/OIDC client ID"
  prompt OIDC_SCOPE "ADFS/OIDC scopes"
  prompt AUTH_GROUP_CLAIM "ADFS/OIDC group claim name"
  prompt AUTH_ADMIN_GROUPS "Comma-separated admin ADFS/OIDC groups"
  prompt AUTH_ADMINS "Comma-separated break-glass admin users/emails"
  prompt FRONTEND_HOST "Frontend route host"
  prompt BACKEND_HOST "Backend route host"
  prompt LLM_EGRESS_CIDR "LLM gateway egress CIDR"
  prompt IDP_EGRESS_CIDR "IdP egress CIDR"
  prompt COMMS_WEBHOOK_URL "Notifications webhook URL (blank to disable)"
  if [[ -n "$COMMS_WEBHOOK_URL" ]]; then
    prompt COMMS_EGRESS_CIDR "Notifications webhook egress CIDR"
  fi

  cmd_values

  echo
  echo "Next required secrets:"
  cat <<EOF
  $PULL_SECRET                  docker-registry pull secret
  $EXTERNAL_DB_SECRET           key: password
  $BACKEND_SECRET               keys: OPENAI_API_KEY, BACKEND_AUTH_SECRET
  $FRONTEND_SECRET              keys: AUTH_SECRET, AUTH_SSO_CLIENT_SECRET, BACKEND_AUTH_SECRET
EOF
  if [[ -n "$INTERNAL_CA_SECRET" ]]; then
    echo "  $INTERNAL_CA_SECRET              key: $INTERNAL_CA_FILENAME"
  fi

  if confirm "Run artifact check now"; then
    cmd_check
  fi
  if confirm "Render Helm chart now"; then
    cmd_render
  fi
  if confirm "Install/upgrade now (runs Alembic migration hook)"; then
    cmd_install
    cmd_status
  else
    cmd_status
  fi
}

check_model() {
  local model="$ROOT_DIR/backend/vendor/models/jina-code-embeddings-0.5b/model.safetensors"
  if [[ ! -s "$model" ]]; then
    echo "missing vendored embedder weights: $model" >&2
    echo "fetch this with git lfs before moving the repo into the air gap" >&2
    exit 1
  fi
  if head -c 80 "$model" | grep -q "git-lfs"; then
    echo "embedder weights are still a Git LFS pointer: $model" >&2
    exit 1
  fi
}

cmd_check() {
  need helm
  [[ -f "$ROOT_DIR/backend/Dockerfile" ]] || { echo "missing backend/Dockerfile" >&2; exit 1; }
  [[ -f "$ROOT_DIR/frontend/Dockerfile" ]] || { echo "missing frontend/Dockerfile" >&2; exit 1; }
  [[ -f "$ROOT_DIR/frontend/package-lock.json" ]] || { echo "missing frontend/package-lock.json" >&2; exit 1; }
  [[ -f "$ROOT_DIR/backend/uv.lock" ]] || { echo "missing backend/uv.lock" >&2; exit 1; }
  [[ -d "$ROOT_DIR/backend/alembic/versions" ]] || { echo "missing backend/alembic/versions" >&2; exit 1; }
  check_model
  echo "air-gap artifact check passed"
}

cmd_todos() {
  echo "TODO: On-premise markers — every place an operator must touch:"
  echo
  if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse >/dev/null 2>&1; then
    git -C "$ROOT_DIR" grep -n "TODO: On-premise\|TODO: On-prem" -- \
      ':!*.lock' ':!*.lockb' ':!node_modules' ':!.venv'
  else
    grep -rn "TODO: On-premise\|TODO: On-prem" \
      --include="*.py" --include="*.ts" --include="*.tsx" \
      --include="*.yaml" --include="*.yml" --include="*.md" \
      --include="*.toml" --include="*.json" --include="*.example" \
      --include="*.sh" --include="Dockerfile*" \
      "$ROOT_DIR" 2>/dev/null
  fi
  echo
  echo "Action: edit each line above before running 'values' / 'install'."
}

# Offline alembic SQL emission. Sandbox-friendly: needs no Postgres connection,
# imports the same env.py as the migration Job. Use this to review the exact
# schema delta before pushing the backend image to your internal registry.
cmd_validate_migrations() {
  local backend_dir="$ROOT_DIR/backend"
  local out="${MIGRATION_SQL_OUT:-$ROOT_DIR/migration.sql}"
  [[ -d "$backend_dir/alembic/versions" ]] || {
    echo "missing backend/alembic/versions" >&2; exit 1
  }
  local runner=""
  if command -v uv >/dev/null 2>&1; then
    runner="uv run"
  elif command -v alembic >/dev/null 2>&1; then
    runner=""
  else
    echo "neither uv nor alembic on PATH; install one before running validate-migrations" >&2
    exit 1
  fi
  ( cd "$backend_dir" && $runner alembic upgrade head --sql ) >"$out"
  echo "wrote offline migration SQL: $out"
  echo "review this file; the in-cluster migration Job will execute the same statements against REMOTE_DB_URL."
}

cmd_build_images() {
  need "${DOCKER:-docker}"
  local docker_bin="${DOCKER:-docker}"
  local backend_args=(
    --build-arg "REGISTRY_PREFIX=${REGISTRY_PREFIX:-docker.io}"
  )
  [[ -n "${DEBIAN_MIRROR:-}" ]] && backend_args+=(--build-arg "DEBIAN_MIRROR=$DEBIAN_MIRROR")
  [[ -n "${PIP_INDEX_URL:-}" ]] && backend_args+=(--build-arg "PIP_INDEX_URL=$PIP_INDEX_URL")
  [[ -n "${PIP_TRUSTED_HOST:-}" ]] && backend_args+=(--build-arg "PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST")
  local frontend_args=()
  [[ -n "${BASE_IMAGE:-}" ]] && frontend_args+=(--build-arg "BASE_IMAGE=$BASE_IMAGE")
  [[ -n "${NPM_REGISTRY:-}" ]] && frontend_args+=(--build-arg "NPM_REGISTRY=$NPM_REGISTRY")

  local backend_tag="$REGISTRY/$BACKEND_REPOSITORY:$IMAGE_TAG"
  local frontend_tag="$REGISTRY/$FRONTEND_REPOSITORY:$IMAGE_TAG"

  echo "Building $backend_tag"
  "$docker_bin" build "$ROOT_DIR/backend" -t "$backend_tag" "${backend_args[@]}"
  echo "Building $frontend_tag"
  "$docker_bin" build "$ROOT_DIR/frontend" -t "$frontend_tag" "${frontend_args[@]}"
  echo "Built:"
  echo "  $backend_tag"
  echo "  $frontend_tag"
}

cmd_push_images() {
  need "${DOCKER:-docker}"
  local docker_bin="${DOCKER:-docker}"
  local backend_tag="$REGISTRY/$BACKEND_REPOSITORY:$IMAGE_TAG"
  local frontend_tag="$REGISTRY/$FRONTEND_REPOSITORY:$IMAGE_TAG"
  "$docker_bin" push "$backend_tag"
  "$docker_bin" push "$frontend_tag"
  echo "Pushed:"
  echo "  $backend_tag"
  echo "  $frontend_tag"
}

cmd_values() {
  mkdir -p "$(dirname "$VALUES_OUT")"
  local ca_bundle_path=""
  local ca_backend_env=""
  local ca_backend_mounts=""
  local ca_frontend_mounts=""
  local comms_egress=""
  if [[ -n "$INTERNAL_CA_SECRET" ]]; then
    ca_bundle_path="$INTERNAL_CA_MOUNT_DIR/$INTERNAL_CA_FILENAME"
    ca_backend_env=$(cat <<EOF
    SSL_CERT_FILE: "$ca_bundle_path"
    REQUESTS_CA_BUNDLE: "$ca_bundle_path"
EOF
)
    ca_backend_mounts=$(cat <<EOF
  extraVolumes:
    - name: internal-ca
      secret:
        secretName: "$INTERNAL_CA_SECRET"
  extraVolumeMounts:
    - name: internal-ca
      mountPath: "$INTERNAL_CA_MOUNT_DIR"
      readOnly: true
EOF
)
    ca_frontend_mounts="$ca_backend_mounts"
  fi
  if [[ -n "$COMMS_EGRESS_CIDR" ]]; then
    comms_egress="    - \"$COMMS_EGRESS_CIDR\""
  fi
  cat >"$VALUES_OUT" <<EOF
# Generated by scripts/airgap_migrate.sh.
# TODO: On-premise - review every value before installing.
global:
  imageRegistry: "$REGISTRY"
  imagePullSecrets:
    - name: "$PULL_SECRET"

backend:
  image:
    repository: "$BACKEND_REPOSITORY"
    tag: "$IMAGE_TAG"
    pullPolicy: IfNotPresent
  env:
    # TODO: On-premise - point these at your OpenAI-compatible internal LLM gateway.
    CODE_AGENT_BASE_URL: "$LLM_BASE_URL"
    CODE_AGENT_MODEL: "gpt-5"
    GENERALIST_AGENT_BASE_URL: "$LLM_BASE_URL"
    GENERALIST_AGENT_MODEL: "gpt-5"
$ca_backend_env
    # TODO: On-premise - set to the public frontend route.
    FRONTEND_URL: "https://$FRONTEND_HOST"
    # TODO: On-premise - list every browser origin allowed to call the backend.
    ALLOWED_ORIGINS: "https://$FRONTEND_HOST"
    ADMIN_GROUPS: "$AUTH_ADMIN_GROUPS"
    ADMIN_USERNAMES: "$AUTH_ADMINS"
    COMMS_WEBHOOK_URL: "$COMMS_WEBHOOK_URL"
  secrets:
    # TODO: On-premise - must contain OPENAI_API_KEY and BACKEND_AUTH_SECRET.
    existingSecret: "$BACKEND_SECRET"
$ca_backend_mounts

frontend:
  image:
    repository: "$FRONTEND_REPOSITORY"
    tag: "$IMAGE_TAG"
    pullPolicy: IfNotPresent
  env:
    API_URL: "https://$BACKEND_HOST"
    # TODO: On-premise - point at your internal OIDC issuer.
    AUTH_SSO_ISSUER: "$OIDC_ISSUER"
    AUTH_SSO_CLIENT_ID: "$OIDC_CLIENT_ID"
    AUTH_SSO_SCOPE: "$OIDC_SCOPE"
    AUTH_GROUP_CLAIM: "$AUTH_GROUP_CLAIM"
    AUTH_ADMIN_GROUPS: "$AUTH_ADMIN_GROUPS"
    AUTH_ADMINS: "$AUTH_ADMINS"
    # TODO: On-premise - set when your IdP uses a private CA mounted in the pod.
    NODE_EXTRA_CA_CERTS: "$ca_bundle_path"
  secrets:
    # TODO: On-premise - must contain AUTH_SECRET, AUTH_SSO_CLIENT_SECRET, and BACKEND_AUTH_SECRET.
    existingSecret: "$FRONTEND_SECRET"
$ca_frontend_mounts

externalDatabase:
  enabled: true
  host: "$EXTERNAL_DB_HOST"
  port: 5432
  database: skynet
  user: skynet
  existingSecret: "$EXTERNAL_DB_SECRET"
  existingSecretKey: password
  composeUrl: true
  sslmode: require

postgres:
  enabled: false
  image:
    repository: "$POSTGRES_REPOSITORY"
    tag: pg16

openshift:
  routes:
    enabled: true
    backend:
      host: "$BACKEND_HOST"
    frontend:
      host: "$FRONTEND_HOST"

networkPolicy:
  enabled: true
  # TODO: On-premise - use the exact IdP / internal service CIDRs for your cluster.
  egressCidrs:
    - "$IDP_EGRESS_CIDR"
$comms_egress
  # TODO: On-premise - use the exact LLM gateway CIDRs and ports.
  llmEgress:
    - cidr: "$LLM_EGRESS_CIDR"
      ports: [443]

migration:
  enabled: true
  command: ["alembic", "upgrade", "head"]
EOF
  echo "wrote $VALUES_OUT"
}

cmd_render() {
  [[ -f "$VALUES_OUT" ]] || cmd_values
  helm lint "$CHART_DIR" -f "$VALUES_OUT"
  helm template "$RELEASE" "$CHART_DIR" -n "$NAMESPACE" -f "$VALUES_OUT" >/tmp/skynet-airgap-rendered.yaml
  echo "rendered manifest: /tmp/skynet-airgap-rendered.yaml"
}

cmd_install() {
  need helm
  [[ -f "$VALUES_OUT" ]] || cmd_values
  helm upgrade --install "$RELEASE" "$CHART_DIR" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    -f "$VALUES_OUT"
}

cmd_status() {
  cat <<EOF
Run:
  kubectl -n $NAMESPACE rollout status deploy/$RELEASE-skynet-backend
  kubectl -n $NAMESPACE rollout status deploy/$RELEASE-skynet-frontend
  kubectl -n $NAMESPACE logs job/$RELEASE-skynet-migrate

Smoke test:
  curl -k https://$FRONTEND_HOST/
  curl -k https://$BACKEND_HOST/health

ADFS / OIDC callback URL:
  https://$FRONTEND_HOST/api/auth/callback/adfs
EOF
}

case "${1:-}" in
  configure) cmd_configure ;;
  todos) cmd_todos ;;
  check) cmd_check ;;
  validate-migrations) cmd_validate_migrations ;;
  build-images) cmd_build_images ;;
  push-images) cmd_push_images ;;
  values) cmd_values ;;
  render) cmd_render ;;
  install) cmd_install ;;
  status) cmd_status ;;
  all)
    cmd_check
    cmd_validate_migrations
    cmd_values
    cmd_render
    cmd_install
    cmd_status
    ;;
  -h|--help|help|"") usage ;;
  *) usage; exit 2 ;;
esac
