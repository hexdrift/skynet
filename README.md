# Skynet

DSPy prompt optimization as a service. Submit datasets + signature/metric code, run GEPA optimizations, serve optimized programs — all through a web UI or REST API.

## Quick Start

### 1. Prerequisites

- Python 3.10+ (3.11 recommended)
- Node.js 18+ and npm
- PostgreSQL 14+
- An LLM API key (OpenAI, Anthropic, etc.)

### 2. Clone and Setup

```bash
git clone <repo-url>
cd skynet
```

### 3. Database

```bash
# Create the database
createdb skynet

# (Optional) Create a test database for running tests
createdb skynet_test
```

### 4. Backend

```bash
cd backend

# Create environment
python -m venv ../.venv
source ../.venv/bin/activate
pip install -e '.[dev]'

# Configure
cp .env.example .env
# Edit .env — set at minimum:
#   OPENAI_API_KEY=sk-...
#   REMOTE_DB_URL=postgresql://youruser@localhost:5432/skynet

# Start
python main.py
```

Backend runs at http://localhost:8000.

### 5. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure
cp .env.example .env.local
# Edit .env.local — defaults work for local development

# Start
npm run dev
```

Frontend runs at http://localhost:3001.

### 6. Open the App

Navigate to http://localhost:3001. If authentication is enabled you'll see a login page, otherwise you'll land directly on the dashboard.

---

## Project Structure

```
skynet/
├── backend/                    Python API + worker
│   ├── main.py                 Entry point
│   ├── .env.example            Configuration template
│   ├── Dockerfile
│   ├── docker-compose.yml      API + PostgreSQL
│   ├── pyproject.toml
│   ├── core/
│   │   ├── api/                FastAPI routes
│   │   ├── storage/            PostgreSQL persistence
│   │   ├── worker/             Background job processing
│   │   ├── registry/           Module & optimizer resolution
│   │   ├── service_gateway/    DSPy orchestration pipeline
│   │   ├── notifications/      Internal comms (Rocket.Chat, Slack, etc.)
│   │   └── models.py           Pydantic models
│   ├── tests/
│   │   ├── test_llm_integration.py   34 real-API tests
│   │   ├── test_load.py              9 load/stress tests
│   │   └── locustfile.py             Sustained load dashboard
│   └── usage_guide/            Notebooks + API client examples
└── frontend/                   Next.js + shadcn/ui
    ├── .env.example            Configuration template
    ├── package.json
    └── src/
        ├── app/                Pages (dashboard, submit wizard, job detail)
        ├── components/         UI components
        └── lib/                API client, types, auth
```

---

## Configuration

### Backend (`backend/.env`)

```bash
# ── Required ──
OPENAI_API_KEY=sk-your-key          # Or any LiteLLM-supported provider
REMOTE_DB_URL=postgresql://user@localhost:5432/skynet

# ── Server ──
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# ── CORS ──
# Comma-separated allowed origins (defaults to localhost:3000,3001)
ALLOWED_ORIGINS=http://localhost:3001,https://yourdomain.com

# ── Worker ──
WORKER_CONCURRENCY=2                # Parallel optimization jobs
WORKER_POLL_INTERVAL=2.0            # Queue poll interval (seconds)
WORKER_STALE_THRESHOLD=600          # Health check threshold (seconds)

# ── Notifications (optional) ──
# COMMS_WEBHOOK_URL=https://chat.yourcompany.com/hooks/webhook-id
# COMMS_CHANNEL=#skynet-notifications
# FRONTEND_URL=https://skynet.yourcompany.com
```

### Frontend (`frontend/.env.local`)

```bash
# ── API ──
NEXT_PUBLIC_API_URL=http://localhost:8000

# ── Auth (NextAuth) ──
AUTH_SECRET=generate-with-openssl-rand-base64-32

# ── ADFS Login (optional — uncomment to enable) ──
# AUTH_ADFS_ISSUER=https://adfs.yourcompany.com/adfs
# AUTH_ADFS_CLIENT_ID=your-client-id
# AUTH_ADFS_CLIENT_SECRET=your-client-secret

# ── Dev Login (active when ADFS is not configured) ──
# Login with any username and password "skynet"
# Set DEV_AUTH=false to disable login entirely
```

---

## Authentication

### Development Mode (default)

When ADFS is not configured, a local credentials login is active:
- **Username**: any value (becomes your display name)
- **Password**: `skynet`

### ADFS (Production)

1. On your ADFS server, register a new Web Application (OpenID Connect)
2. Set redirect URI: `https://your-app/api/auth/callback/adfs`
3. Enable scopes: `openid`, `profile`, `email`
4. Copy Client ID and Secret to `frontend/.env.local`

When authenticated, the username auto-fills in the submit form from the ADFS session.

### No Authentication

Set `DEV_AUTH=false` in `frontend/.env.local` (with ADFS env vars unset) to disable login entirely.

---

## Notifications

Skynet sends Hebrew notifications to your internal messaging platform when jobs are submitted or completed.

### Setup

1. Create an incoming webhook in your messaging platform (Rocket.Chat, Slack, Teams, etc.)
2. Set `COMMS_WEBHOOK_URL` in `backend/.env`
3. Optionally set `COMMS_CHANNEL` and `FRONTEND_URL`

### Messages

| Event | Message |
|-------|---------|
| Job submitted | 🚀 אופטימיזציה חדשה — user, optimizer, model, [link to monitor] |
| Job succeeded | ✅ אופטימיזציה הושלמה — user, scores, [link to results] |
| Job failed | ❌ אופטימיזציה נכשלה — user, error, [link to details] |
| Job cancelled | ⚠️ אופטימיזציה בוטלה — user, [link to details] |

When `COMMS_WEBHOOK_URL` is not set, notifications are silently skipped.

### Adapting to Your Platform

Edit `backend/core/notifications/comms.py` — the `send_message()` function sends a JSON payload to the webhook URL. Adjust the payload format for your platform:

```python
# Rocket.Chat / Slack:  {"text": "...", "channel": "#room"}
# Teams:                {"text": "..."}
# Custom:               adapt as needed
```

---

## Serving Optimized Programs

After a successful optimization, you can run inference on the optimized program:

```bash
# Check what fields the program expects
curl http://localhost:8000/serve/{optimization_id}/info

# Run inference
curl -X POST http://localhost:8000/serve/{optimization_id} \
  -H 'Content-Type: application/json' \
  -d '{"inputs": {"question": "What is 7+3?"}}'
```

The frontend provides a built-in playground on the job detail page — fill in the input fields and click "הרץ תוכנית".

---

## Supported Optimization Configurations

| Module | Optimizer | Job Type | Notes |
|--------|-----------|----------|-------|
| predict | gepa | run | Requires `reflection_model_config` and 5-arg metric |
| cot | gepa | run | Same as above with CoT |
| predict | gepa | grid_search | GEPA grid search over model pairs |
| cot | gepa | grid_search | GEPA grid search with CoT |

### Model Config Options

| Field | Description |
|-------|-------------|
| `name` | Model identifier (e.g., `gpt-4o-mini`, `o3-mini`, `claude-sonnet-4-20250514`) |
| `base_url` | Custom endpoint (Azure, vLLM, local LLMs) |
| `temperature` | 0.0–2.0 |
| `max_tokens` | Max output tokens |
| `top_p` | Nucleus sampling |
| `extra.api_key` | Per-request API key (not stored in DB) |
| `extra.reasoning_effort` | For o-series models: `low`, `medium`, `high` |

---

## Docker

```bash
cd backend
docker compose up --build
```

This starts the API + PostgreSQL. The frontend must be deployed separately (Vercel, Docker, etc.).

---

## Testing

### Backend Integration Tests (real API calls)

```bash
cd backend

# Start the server first
python main.py &

# Run all 34 integration tests (requires OPENAI_API_KEY)
python -m pytest tests/test_llm_integration.py -v

# Run load tests (9 tests)
python -m pytest tests/test_load.py -v

# Sustained load testing dashboard
locust -f tests/locustfile.py --host=http://localhost:8000
```

### Frontend

```bash
cd frontend
npm run build    # Type check + build
```

---

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run` | Submit optimization run |
| `POST` | `/grid-search` | Submit grid search |
| `GET` | `/optimizations` | List optimizations (filterable, paginated) |
| `GET` | `/optimizations/{id}` | Full optimization detail |
| `GET` | `/optimizations/{id}/summary` | Dashboard-friendly summary |
| `GET` | `/optimizations/{id}/logs` | Optimization logs (filterable by level) |
| `GET` | `/optimizations/{id}/payload` | Original submission payload |
| `GET` | `/optimizations/{id}/artifact` | Download optimized program |
| `GET` | `/optimizations/{id}/grid-result` | Grid search results |
| `GET` | `/optimizations/{id}/stream` | SSE real-time updates |
| `POST` | `/optimizations/{id}/cancel` | Cancel active optimization |
| `DELETE` | `/optimizations/{id}` | Delete terminal optimization |
| `POST` | `/optimizations/{id}/clone` | Clone an optimization |
| `POST` | `/optimizations/{id}/retry` | Retry a failed or cancelled optimization |
| `GET` | `/serve/{id}/info` | Program signature info |
| `POST` | `/serve/{id}` | Run inference on optimized program |
| `GET` | `/health` | Health check |
| `GET` | `/queue` | Queue status |

### Error Format

All errors return:
```json
{"error": "<type>", "detail": "Human-readable message"}
```

---

## Extensibility

Register custom modules and optimizers in `main.py`:

```python
from core import ServiceRegistry, create_app

registry = ServiceRegistry()
registry.register_module("my_module", my_module_factory)
registry.register_optimizer("my_optimizer", my_optimizer_factory)

app = create_app(registry=registry)
```

---

## Client Usage Guide

See [`backend/usage_guide/index.html`](backend/usage_guide/index.html) for notebook examples and API client classes.
