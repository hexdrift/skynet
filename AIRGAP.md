# Air-Gap Deployment Guide

How to deploy Skynet on an on-premise, internet-isolated network.

This guide is **a navigator, not a how-to.** Every value you need to substitute for your environment is marked in-code with a `TODO: On-premise` comment next to a placeholder. Read this once, then drive the rollout from `git grep`.

---

## Step 1 — Find every placeholder

```bash
git grep -n "TODO: On-premise"
```

Each hit is a single substitution: replace `artifactory.your-company.com`, `your-company.com`, or the placeholder URL with the real value for your network. Hits live in:

- `backend/Dockerfile`, `backend/pyproject.toml`, `backend/docker-compose.yml`
- `frontend/Dockerfile`, `frontend/.npmrc`
- `backend/.env.example`, `frontend/.env.example`

Copy the example envs into real ones first:

```bash
cp backend/.env.example  backend/.env
cp frontend/.env.example frontend/.env.local
```

Then walk the TODOs in those files too.

## Step 2 — Pull LFS artifacts

The recommendations embedder model (`jina-code-embeddings-0.5b`, ~942 MB) is vendored under `backend/vendor/models/` and tracked via Git LFS so it ships with the repo. After cloning:

```bash
git lfs install        # one-time per machine
git lfs pull           # fetches the model weights
```

The embedder loads from this local path by default — no Hugging Face download at runtime. Override with `RECOMMENDATIONS_EMBEDDING_MODEL=/path/to/other/model` if needed, or set `RECOMMENDATIONS_ENABLED=false` to skip the feature entirely.

## Step 3 — Verify the build is hermetic

After substituting placeholders:

```bash
# In a network-isolated build host, this must succeed without any DNS
# resolution to the public internet:
docker compose -f backend/docker-compose.yml build
docker build -t skynet-frontend frontend/
```

If a build step fails reaching the public internet, that's a TODO you missed.

## Step 4 — Pre-flight checklist

Before pointing production traffic at the deployment:

- [ ] `git grep "TODO: On-premise"` returns zero hits in your fork (or every remaining hit is intentional).
- [ ] `git lfs ls-files` shows `model.safetensors` is fetched (not a pointer file).
- [ ] Both Docker images build inside the air-gapped network.
- [ ] Postgres reachable; `pgvector` extension installed (`CREATE EXTENSION vector;`).
- [ ] OIDC IdP reachable from the frontend container; SSO round-trip works.
- [ ] LLM gateway reachable from the backend container; one test job completes end-to-end.
- [ ] Network egress firewall in place (defense-in-depth — see Caveats below).
- [ ] Smoke test: load `/`, sign in via SSO, submit a tiny optimization job, watch worker logs for any outbound DNS attempts.

---

## What's already air-gap-clean (no action needed)

For reference, the audit confirmed these are already safe:

- **Scalar API docs** — vendored under `backend/core/api/static/scalar/`, fonts rewritten to local paths. Telemetry and agent panel disabled.
- **Fonts** — `@fontsource-variable/heebo` and `inter` are npm packages bundled at build (no Google Fonts CDN).
- **Embedder model** — `jina-code-embeddings-0.5b` vendored under `backend/vendor/models/` via Git LFS; loaded from disk, no runtime download.
- **Telemetry** — no Sentry, GA, PostHog, Datadog, OTLP, Segment, or pixel trackers anywhere. `litellm.telemetry` is forced off.
- **Storage** — Postgres only, no S3 / GCS / Azure Blob / Redis.
- **MCP** — `FastMCP` mounts at `/mcp`, loopback only. Generalist agent's MCP client defaults to `http://localhost:8000/mcp/`.
- **Auth providers** — only NextAuth Credentials and a generic OIDC client. No Google / GitHub / external OAuth.
- **JSON-LD `@context: schema.org`** — static identifier string, never fetched.

---

## Caveats

- **`POST /models/discover`** (`backend/core/api/routers/models.py:175-176`) calls `urlopen()` with a user-supplied `base_url`. Behaves as designed for internal model discovery, but it is an exfiltration vector if egress is not firewalled at the network layer.
- **`litellm` provider URLs** — `model_catalog.py` lists public-provider hostnames (OpenAI, Anthropic, etc.) for display, but a job only contacts the URL implied by the model id the user picks. Block public egress at the firewall as defense-in-depth, in case a user pastes a public-provider key into the model catalog.
- **First-run model downloads** — the recommendations embedder is the only model used at runtime, and it ships vendored under `backend/vendor/models/`. If you later add a feature that needs a different model, vendor it the same way (drop under `backend/vendor/models/<name>/`, point `RECOMMENDATIONS_EMBEDDING_MODEL` or a new setting at it) so the air-gap story stays clean.
