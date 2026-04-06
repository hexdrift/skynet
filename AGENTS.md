# AGENTS.md — Skynet Codebase Index

> DSPy prompt optimization as a service. Full-stack: FastAPI backend + Next.js frontend + PostgreSQL.

## Tech Stack
- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, DSPy, LiteLLM, PostgreSQL
- **Frontend**: Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, Framer Motion, NextAuth
- **Package Managers**: uv (backend), npm (frontend)

## Project Layout

```
├── backend/                     FastAPI API + background worker
│   ├── main.py                  Entry point (uvicorn, registry setup)
│   ├── pyproject.toml           Python deps (uv)
│   ├── .env / .env.example      Config (DB, API keys, worker settings)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── core/
│   │   ├── __init__.py          Exports: ServiceRegistry, create_app
│   │   ├── models.py            Pydantic models (JobRequest, JobResponse, etc.)
│   │   ├── constants.py         Shared constants
│   │   ├── exceptions.py        Custom exception classes
│   │   ├── api/
│   │   │   ├── app.py           FastAPI app factory, all route handlers
│   │   │   └── converters.py    Data conversion utilities
│   │   ├── storage/
│   │   │   ├── base.py          Abstract storage interface
│   │   │   ├── local.py         In-memory job store
│   │   │   └── remote.py        PostgreSQL job store (SQLAlchemy)
│   │   ├── worker/
│   │   │   ├── engine.py        Background job processor (poll + execute)
│   │   │   └── log_handler.py   Structured logging for jobs
│   │   ├── registry/
│   │   │   ├── core.py          Module/optimizer registration
│   │   │   └── resolvers.py     Dynamic module/optimizer resolution
│   │   ├── service_gateway/
│   │   │   ├── core.py          DSPy orchestration pipeline
│   │   │   ├── data.py          Dataset loading/parsing
│   │   │   ├── language_models.py  LM configuration via LiteLLM
│   │   │   ├── optimizers.py    MIPROv2/GEPA optimizer setup
│   │   │   ├── artifacts.py     Optimized program storage
│   │   │   └── progress.py      Job progress tracking
│   │   └── notifications/
│   │       ├── comms.py         Webhook sender (Slack/Rocket.Chat)
│   │       └── notifier.py      Event-driven notification dispatch
│   ├── tests/
│   │   ├── test_llm_integration.py  34 integration tests (real API)
│   │   ├── test_load.py             9 load/stress tests
│   │   └── locustfile.py            Sustained load testing
│   └── usage_guide/             Notebooks + API client examples
│
├── frontend/                    Next.js 16 + shadcn/ui
│   ├── package.json             Node deps
│   ├── .env.local / .env.example  Config (API URL, auth)
│   ├── next.config.ts
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx       Root layout (RTL, fonts, theme)
│   │   │   ├── page.tsx         Dashboard (job list)
│   │   │   ├── login/page.tsx   Auth login page
│   │   │   ├── submit/page.tsx  Job submission wizard
│   │   │   ├── jobs/[id]/page.tsx  Job detail + results + playground
│   │   │   ├── robots.ts       SEO robots
│   │   │   └── sitemap.ts      SEO sitemap
│   │   ├── components/
│   │   │   ├── app-shell.tsx    Main layout shell
│   │   │   ├── sidebar.tsx      Navigation sidebar
│   │   │   ├── motion.tsx       Framer Motion wrappers
│   │   │   ├── excel-filter.tsx Dataset filter UI
│   │   │   ├── session-provider.tsx  NextAuth session
│   │   │   ├── theme-provider.tsx    Dark/light theme
│   │   │   ├── toast-container.tsx   Notifications
│   │   │   └── ui/             shadcn/ui primitives (button, card, dialog, etc.)
│   │   ├── lib/
│   │   │   ├── api.ts          Backend API client
│   │   │   ├── auth.ts         NextAuth configuration
│   │   │   ├── types.ts        TypeScript types
│   │   │   ├── constants.ts    Shared constants
│   │   │   ├── parse-dataset.ts  Excel/CSV parser
│   │   │   └── utils.ts        Utility functions
│   │   └── middleware.ts       Auth middleware
│
├── docs/                        DSPy/FastAPI/Next.js reference docs
├── scripts/
│   ├── setup-init.sh           First-time setup script
│   └── setup-maintenance.sh    Maintenance/update script
├── Justfile                    Task runner aliases
└── README.md                   Full project documentation
```

## Key URLs
- **Frontend**: http://localhost:3001
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Running
```bash
# Backend
cd backend && uv run python main.py

# Frontend
cd frontend && npm run dev
```

## Testing
```bash
# Backend integration tests (requires running server + OPENAI_API_KEY)
cd backend && uv run pytest tests/test_llm_integration.py -v

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
