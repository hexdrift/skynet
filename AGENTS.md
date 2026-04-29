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
│   │   └── unit/                    Unit tests (no DB / no LLM / no live server)
│   │       ├── test_config.py
│   │       ├── test_constants.py
│   │       ├── test_exceptions.py
│   │       ├── test_i18n_catalog_boundary.py
│   │       └── test_main_importable.py
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
│   │   │   ├── lib/             api client, auth, formatters, validation, utils
│   │   │   ├── types/           Shared TypeScript types
│   │   │   └── constants/       dspy-constants, job-status
│   │   └── components/ui/       shadcn/ui primitives (button, card, dialog, etc.)
│
├── scripts/
│   └── generate_i18n.py         Regenerate typed i18n constants from i18n/locales/he.json
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

## Commenting, docstring & import style (MANDATORY — apply to all backend Python, every session)

These rules are durable. They apply to every backend Python file (under `backend/`, excluding `.venv/`, `__pycache__/`, and `alembic/versions/`) and to every future change. New code follows them; existing code is brought into compliance whenever it is touched.

- **Google-style docstrings on every function and method (public and private).** Format: a one-line imperative summary, then `Args:`, `Returns:`, and (only when the failure mode is non-obvious) `Raises:`. Skip the `Args:` / `Returns:` blocks only when **both** are trivially typed and the summary already covers them (e.g. tests that take no args and assert; private one-liners). Module docstrings are required at the top of every file.
- **Imports only at the top of the file. No exceptions.** No `import` inside a function, method, or conditional block anywhere except module top. Optional deps go in a module-level `try/except ImportError` that aliases the symbol to ``None``; tests that need fresh re-imports use ``importlib.import_module`` (a function call, not an ``import`` statement); circular imports are resolved structurally (slim `__init__.py`, leaf-module splits, `TYPE_CHECKING` blocks) — never with inline imports.
- **No WHAT-comments.** Don't restate what code does, label sections, or echo identifiers ("# loop over users", "# call API"). If a competent reader can understand the line by reading the line, the comment is dead weight — delete it.
- **WHY-comments only.** Comments are reserved for non-obvious intent: a hidden constraint, a workaround for a specific bug, surprising behavior, a subtle invariant, a non-trivial design decision, or a tracking ticket. If deleting the comment wouldn't confuse a future reader, the comment shouldn't exist.
- **Pydantic class docstrings are part of the OpenAPI contract** — see "Backend — Pydantic docstring OpenAPI drift" below before adding/removing them on `BaseModel` subclasses.

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
