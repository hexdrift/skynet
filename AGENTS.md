# AGENTS.md — Skynet Codebase Index

> DSPy prompt optimization as a service. Full-stack: FastAPI backend + Next.js frontend + PostgreSQL.

## Tech Stack
- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, DSPy, LiteLLM, PostgreSQL
- **Frontend**: Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, Framer Motion, NextAuth
- **Package Managers**: pip (backend), npm (frontend)

## Project Layout

```
├── backend/                     FastAPI API + background worker
│   ├── main.py                  Entry point (uvicorn, registry setup)
│   ├── pyproject.toml           Python deps
│   ├── .env / .env.example      Config (DB, API keys, worker settings)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── core/
│   │   ├── __init__.py          Exports: ServiceRegistry, create_app
│   │   ├── constants.py         Shared constants
│   │   ├── exceptions.py        Custom exception classes
│   │   ├── models/              Pydantic models (split by domain)
│   │   │   ├── common.py        Shared base models
│   │   │   ├── submissions.py   Job submission models
│   │   │   ├── optimizations.py Optimization result models
│   │   │   ├── analytics.py     Analytics/metrics models
│   │   │   ├── artifacts.py     Artifact storage models
│   │   │   ├── results.py       Result/output models
│   │   │   ├── serve.py         Serving/inference models
│   │   │   ├── templates.py     Template models
│   │   │   ├── telemetry.py     Telemetry models
│   │   │   ├── validation.py    Validation models
│   │   │   └── infra.py         Infrastructure models
│   │   ├── api/
│   │   │   ├── app.py           FastAPI app factory, route wiring
│   │   │   ├── converters.py    Data conversion utilities
│   │   │   ├── static/scalar/   Bundled Scalar API docs (offline)
│   │   │   └── routers/         Domain routers (factory pattern)
│   │   │       ├── analytics.py
│   │   │       ├── code_validation.py
│   │   │       ├── models.py
│   │   │       ├── optimizations.py
│   │   │       ├── optimizations_meta.py
│   │   │       ├── serve.py
│   │   │       ├── submissions.py
│   │   │       └── templates.py
│   │   ├── storage/
│   │   │   ├── base.py          Abstract storage interface
│   │   │   ├── models.py        SQLAlchemy ORM models
│   │   │   └── remote.py        PostgreSQL job store
│   │   ├── worker/
│   │   │   ├── engine.py        Background job processor (poll + execute)
│   │   │   ├── log_handler.py   Structured logging for jobs
│   │   │   └── subprocess_runner.py  Subprocess execution
│   │   ├── registry/
│   │   │   ├── core.py          Module/optimizer registration
│   │   │   └── resolvers.py     Dynamic module/optimizer resolution
│   │   ├── service_gateway/
│   │   │   ├── core.py          DSPy orchestration pipeline
│   │   │   ├── data.py          Dataset loading/parsing
│   │   │   ├── language_models.py  LM configuration via LiteLLM
│   │   │   ├── optimizers.py    GEPA optimizer setup
│   │   │   ├── artifacts.py     Optimized program storage
│   │   │   ├── progress.py      Job progress tracking
│   │   │   └── validators.py    Input validation
│   │   └── notifications/
│   │       ├── comms.py         Webhook sender (Slack/Rocket.Chat)
│   │       └── notifier.py      Event-driven notification dispatch
│   ├── tests/
│   │   ├── test_llm_integration.py  Integration tests (real API)
│   │   ├── test_load.py             Load/stress tests
│   │   ├── locustfile.py            Sustained load testing
│   │   └── unit/                    Unit tests
│   │       ├── test_helpers.py
│   │       ├── test_models.py
│   │       ├── test_quota.py
│   │       ├── test_routers.py
│   │       └── test_validators.py
│   └── usage_guide/             Notebooks + API client examples
│
├── frontend/                    Next.js 16 + shadcn/ui
│   ├── package.json             Node deps
│   ├── .env.local / .env.example  Config (API URL, auth)
│   ├── next.config.ts
│   ├── src/
│   │   ├── app/                 Thin route wrappers
│   │   │   ├── layout.tsx       Root layout (RTL, fonts, theme)
│   │   │   ├── page.tsx         Dashboard → features/dashboard
│   │   │   ├── login/page.tsx   Auth login page
│   │   │   ├── submit/page.tsx  Job submission → features/submit
│   │   │   ├── optimizations/[id]/  Job detail → features/optimizations
│   │   │   ├── compare/page.tsx Compare jobs → features/compare
│   │   │   ├── api/auth/        NextAuth API route
│   │   │   ├── robots.ts        SEO robots
│   │   │   └── sitemap.ts       SEO sitemap
│   │   ├── features/            Feature slices (see pattern below)
│   │   │   ├── dashboard/       Job list, analytics, bulk actions
│   │   │   ├── submit/          Job submission wizard + model picker
│   │   │   ├── optimizations/   Job detail, results, logs, serve, export
│   │   │   ├── compare/         Side-by-side job comparison
│   │   │   ├── sidebar/         Navigation sidebar
│   │   │   ├── tutorial/        Interactive tutorial overlay
│   │   │   └── shared/          Cross-feature shared messages
│   │   ├── shared/              Shared UI, hooks, types, utilities
│   │   │   ├── ui/              Reusable components (motion, excel-filter, metric-card, etc.)
│   │   │   ├── charts/          Recharts chart components
│   │   │   ├── hooks/           use-api-call, use-debounce, use-local-storage
│   │   │   ├── layout/          app-shell, splash-screen
│   │   │   ├── providers/       session, theme, toast providers
│   │   │   ├── lib/             api client, formatters, validation, utils
│   │   │   ├── types/           Shared TypeScript types
│   │   │   └── constants/       dspy-constants, job-status
│   │   ├── components/ui/       shadcn/ui primitives (button, card, dialog, etc.)
│   │   └── lib/auth.ts          NextAuth configuration
│
├── scripts/
│   └── update_scalar.sh         Rebuild bundled Scalar API docs
├── Justfile                     Task runner (just <recipe>)
└── README.md                    Full project documentation
```

## Key URLs
- **Frontend**: http://localhost:3001
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/reference (Scalar UI)

## Running
```bash
# Backend
cd backend && python main.py

# Frontend
cd frontend && npm run dev
```

## Testing
```bash
# Backend unit tests
cd backend && pytest tests/unit/ -v

# Backend integration tests (requires running server + OPENAI_API_KEY)
cd backend && pytest tests/test_llm_integration.py -v

# Frontend type check
cd frontend && npm run build
```

## Database
- PostgreSQL: `skynet` (main), `skynet_test` (tests)
- Connection via `REMOTE_DB_URL` in `backend/.env`
- SQLAlchemy ORM with async support

## Auth
- Dev mode: any username, password "skynet"
- Production: ADFS/OpenID Connect via NextAuth
- Configurable via `frontend/.env.local`

## RTL/Hebrew
- UI is RTL (Hebrew) by default
- Notification messages are in Hebrew

## Refactoring rules

### Backend — Pydantic docstring OpenAPI drift

When extracting a FastAPI route from `app.py` into a domain router, any
inline `class FooRequest(BaseModel)` you move must **keep or drop docstrings
exactly as in the source**. Pydantic emits the class docstring into the
OpenAPI schema as `components.schemas.FooRequest.description` — add one
where there wasn't one (or remove one that existed) and the `openapi.json`
hash drifts, failing the regression gate. If you need to document the
class for readers, use a comment above the class, not a docstring.

### Backend — domain router factory pattern

Extracted routers live under `backend/core/api/routers/`. Each exposes a
`create_<domain>_router(*, deps...) -> APIRouter` factory. `create_app`
wires them via `app.include_router(create_<domain>_router(...))`. Use
closures over factory parameters, not module-level globals, so the routes
can be tested in isolation with mocked dependencies.

### Frontend — feature slice pattern

Per-feature code lives under `frontend/src/features/<feature>/`:
- `components/` — presentational + orchestrator
- `hooks/` — state machines and data fetching
- `lib/` — pure functions (validators, formatters, builders)
- `constants.ts` — feature-local constants
- `index.ts` — public API; other features import only from here

`app/<feature>/page.tsx` should be a thin wrapper over the feature slice's
orchestrator component.
