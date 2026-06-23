# Skynet Helm Chart

Production-grade Helm chart for the Skynet platform — FastAPI backend with
embedded worker, Next.js frontend, and an optional bundled pgvector Postgres.
Targets OpenShift; horizontally scalable via HPAs and a DB-backed worker
claim queue (Wave 2).

## Quick install

```bash
# 1. From the repo root, render & inspect first:
helm lint deploy/helm/skynet
helm template skynet deploy/helm/skynet > /tmp/rendered.yaml

# 2. Install (uses bundled pgvector by default):
helm upgrade --install skynet deploy/helm/skynet \
  --namespace skynet --create-namespace \
  --set backend.image.repository=artifactory.example.com/skynet/backend \
  --set frontend.image.repository=artifactory.example.com/skynet/frontend \
  --set backend.image.tag=0.1.0 \
  --set frontend.image.tag=0.1.0 \
  --set backend.secrets.data.OPENAI_API_KEY=sk-...

# 3. Dev install (single replica, looser probes, no HPA/PDB):
helm upgrade --install skynet deploy/helm/skynet \
  -n skynet-dev --create-namespace \
  -f deploy/helm/skynet/values-dev.yaml
```

## What gets deployed

| Component | Kind                      | Default replicas | HPA range |
|-----------|---------------------------|------------------|-----------|
| backend   | Deployment + Service + Route + HPA + PDB + NetworkPolicy | 2 | 2–8 |
| frontend  | Deployment + Service + Route + HPA + PDB + NetworkPolicy | 2 | 2–4 |
| pgbouncer | Deployment + Service (optional, transaction pooling) | 2 | n/a |
| postgres  | StatefulSet + headless Service (gated by `postgres.enabled`) | 1 | n/a |
| migrate   | Job (pre-install / pre-upgrade hook, weight -5) | one-shot | n/a |

## Common upgrade flows

```bash
# Bump image tag only:
helm upgrade skynet deploy/helm/skynet --reuse-values \
  --set backend.image.tag=0.2.0 --set frontend.image.tag=0.2.0

# Switch to external pgvector (e.g. managed RDS / Crunchy):
helm upgrade skynet deploy/helm/skynet --reuse-values \
  --set postgres.enabled=false \
  --set externalDatabase.enabled=true \
  --set externalDatabase.host=pg.internal \
  --set externalDatabase.user=skynet \
  --set externalDatabase.database=skynet \
  --set externalDatabase.password='***'
```

## Production checklist

- [ ] `global.imageRegistry` set to your internal Artifactory. It must prefix
      ALL FOUR images — `skynet/backend`, `skynet/frontend`, `pgvector/pgvector:pg16`,
      and `edoburu/pgbouncer`. The last two are easy to forget on the bundled-DB /
      pooler paths and will `ImagePullBackOff` from Docker Hub otherwise.
- [ ] `global.imagePullSecrets` references a `kubernetes.io/dockerconfigjson` secret.
- [ ] `externalDatabase.enabled=true` pointing at managed pgvector (set `postgres.enabled=false`).
- [ ] External-DB deployments (`postgres.enabled=false`) MUST set `networkPolicy.dbEgress`
      to the managed Postgres subnet, or the backend pool and migration Job cannot reach it.
- [ ] Backend secrets sourced from an external secret store (set `backend.secrets.existingSecret`).
- [ ] `frontend.secrets.data.AUTH_SECRET` rotated (`openssl rand -base64 32`).
- [ ] OIDC vars populated: `AUTH_SSO_ISSUER`, `AUTH_SSO_CLIENT_ID`, `AUTH_SSO_CLIENT_SECRET`.
- [ ] `openshift.routes.*.host` pinned to a real DNS name with a valid certificate.
- [ ] `networkPolicy.egressCidrs` narrowed to your LLM gateway + IdP CIDRs.
- [ ] An empty egress allowlist renders `0.0.0.0/0` (NOT air-gapped). After install,
      verify with `kubectl get networkpolicy <release>-skynet-backend -o yaml` that the
      egress `ipBlock` is NOT `0.0.0.0/0`.
- [ ] `backend.env.ALLOWED_ORIGINS` lists every front-door host.

## Key values

| Value | Purpose |
|-------|---------|
| `backend.env.WORKER_CONCURRENCY` | Threaded worker fan-out per replica (default 4). |
| `backend.env.WORKER_POLL_INTERVAL` | DB poll cadence in seconds (default 2.0). |
| `backend.env.EMBEDDINGS_ENABLED` | Master switch for the embedding/recommendation pipeline. |
| `backend.env.EMBEDDINGS_BASE_URL` | Internal OpenAI-compatible embedding API base URL. |
| `networkPolicy.embeddingEgress` | Optional backend egress allowlist when the embedding API uses a separate CIDR. |
| `backend.env.CODE_AGENT_BASE_URL` | Override for internal OpenAI-compatible gateway. |
| `frontend.env.API_URL` | Runtime backend address. Empty → in-cluster service. |
| `openshift.routes.backend.annotations` | Default `haproxy.router.openshift.io/timeout: 5m` for long optimization runs. |
| `backend.autoscaling.queueDepth` | External metric target for pending jobs; requires Prometheus Adapter. CPU remains as fallback. |
| `pgbouncer.enabled` | Optional transaction-pooler in front of Postgres; backend pods set `DB_PGBOUNCER_TRANSACTION_MODE=true` when enabled. |
| `migration.command` | Pre-install/upgrade hook command; default `["alembic","upgrade","head"]`. Override to `["alembic","stamp","342f7449be26"]` once when adopting a DB already at the baseline. |

## Uninstall

```bash
helm uninstall skynet -n skynet
# Bundled Postgres PVCs survive uninstall by design — clean up explicitly:
kubectl delete pvc -l app.kubernetes.io/instance=skynet -n skynet
```
