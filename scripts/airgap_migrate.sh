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
LLM_BASE_URL="${LLM_BASE_URL:-https://llm-gateway.internal/v1}"
OIDC_ISSUER="${OIDC_ISSUER:-https://idp.internal/realms/skynet}"
OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-skynet}"
FRONTEND_HOST="${FRONTEND_HOST:-skynet.apps.internal}"
BACKEND_HOST="${BACKEND_HOST:-skynet-api.apps.internal}"
LLM_EGRESS_CIDR="${LLM_EGRESS_CIDR:-10.0.5.0/24}"
IDP_EGRESS_CIDR="${IDP_EGRESS_CIDR:-10.0.6.0/24}"

usage() {
  cat <<'EOF'
Usage: scripts/airgap_migrate.sh <command>

Commands:
  configure      Prompt for on-prem values, write values file, optionally render/install.
  check          Verify local repo artifacts needed for an air-gapped rollout.
  values         Generate deploy/helm/skynet/values-airgap.generated.yaml.
  render         Run helm lint + helm template with the generated values.
  install        Run helm upgrade --install; the Helm migration hook runs first.
  status         Print rollout status commands for backend/frontend.
  all            Run check, values, render, install, status.

Common environment overrides:
  RELEASE=skynet
  NAMESPACE=skynet
  REGISTRY=artifactory.example.com/skynet
  IMAGE_TAG=2026.04.30
  PULL_SECRET=artifactory-pull-secret
  EXTERNAL_DB_HOST=pgvector.internal
  EXTERNAL_DB_SECRET=skynet-db-password
  LLM_BASE_URL=https://llm-gateway.internal/v1
  OIDC_ISSUER=https://idp.internal/realms/skynet
  OIDC_CLIENT_ID=skynet
  FRONTEND_HOST=skynet.apps.internal
  BACKEND_HOST=skynet-api.apps.internal
  LLM_EGRESS_CIDR=10.0.5.0/24
  IDP_EGRESS_CIDR=10.0.6.0/24

Assumptions:
  - backend/frontend/postgres images already exist in the internal registry.
  - the namespace already has image pull, DB password, AUTH_SECRET, and OIDC
    client-secret Kubernetes secrets.
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
  prompt LLM_BASE_URL "Internal OpenAI-compatible LLM base URL"
  prompt OIDC_ISSUER "Internal OIDC issuer URL"
  prompt OIDC_CLIENT_ID "OIDC client ID"
  prompt FRONTEND_HOST "Frontend route host"
  prompt BACKEND_HOST "Backend route host"
  prompt LLM_EGRESS_CIDR "LLM gateway egress CIDR"
  prompt IDP_EGRESS_CIDR "IdP egress CIDR"

  cmd_values

  echo
  echo "Next required secrets:"
  cat <<EOF
  $PULL_SECRET                  docker-registry pull secret
  $EXTERNAL_DB_SECRET           key: password
  skynet-backend-secrets        key: OPENAI_API_KEY
  skynet-frontend-secrets       keys: AUTH_SECRET, AUTH_SSO_CLIENT_SECRET
EOF

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

cmd_values() {
  mkdir -p "$(dirname "$VALUES_OUT")"
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
    # TODO: On-premise - set to the public frontend route.
    FRONTEND_URL: "https://$FRONTEND_HOST"
    # TODO: On-premise - list every browser origin allowed to call the backend.
    ALLOWED_ORIGINS: "https://$FRONTEND_HOST"
  secrets:
    # TODO: On-premise - prefer an externally managed secret in production.
    existingSecret: "skynet-backend-secrets"

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
    AUTH_SSO_SCOPE: "openid profile email"
    # TODO: On-premise - set when your IdP uses a private CA mounted in the pod.
    NODE_EXTRA_CA_CERTS: ""
  secrets:
    # TODO: On-premise - must contain AUTH_SECRET and AUTH_SSO_CLIENT_SECRET.
    existingSecret: "skynet-frontend-secrets"

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
EOF
}

case "${1:-}" in
  configure) cmd_configure ;;
  check) cmd_check ;;
  values) cmd_values ;;
  render) cmd_render ;;
  install) cmd_install ;;
  status) cmd_status ;;
  all)
    cmd_check
    cmd_values
    cmd_render
    cmd_install
    cmd_status
    ;;
  -h|--help|help|"") usage ;;
  *) usage; exit 2 ;;
esac
