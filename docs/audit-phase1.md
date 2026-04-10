# Phase 1 Audit — Aggregated Findings

Aggregated from four parallel Explore agents (frontend structural, backend
structural, contracts drift, dead-code sweep) on the HEAD that captured
the Phase 0 regression baselines.

This is a read-only audit. No refactor proposals. These findings feed
Phase 2 (frontend) and Phase 3 (backend) decisions.

## Frontend (`frontend/src`)

### Files > 300 lines — primary split candidates

| Lines | File | One-liner |
|---|---|---|
| 2164 | `app/page.tsx` | Dashboard — grid view, table view, charts, filters all inline. **#1 priority.** |
| 973 | `app/optimizations/[id]/page.tsx` | Job detail — mostly delegated after the earlier `#13` work; serve playground orchestration remains |
| 780 | `features/submit/hooks/use-submit-wizard.ts` | 6-step wizard state machine; single file |
| 733 | `components/sidebar.tsx` | `Sidebar()` 354L + inline `JobRow()` 300L + `StatusDot()` 22L |
| 606 | `lib/tutorial-steps.ts` | Hardcoded tutorial sequence definitions |
| 591 | `features/optimizations/components/DataTab.tsx` | Data explorer (table + sort + filter) |
| 560 | `lib/tutorial-demo-data.ts` | Demo simulation data |
| 534 | `app/compare/page.tsx` | Compare page — formatters + score cards still inline |
| 524 | `lib/api.ts` | API client (fetch wrapper + dedup cache + all endpoints) |
| 517 | `features/optimizations/components/GridOverview.tsx` | Grid-search pair matrix |
| 513 | `components/analytics-charts.tsx` | 6 recharts components in one file |
| 463 | `components/excel-filter.tsx` | Column header + sort + multi-select filter |

### God functions / components > 80 lines

- `app/page.tsx:141` `DashboardPage` — ~2000L single component body
- `app/optimizations/[id]/page.tsx:83` `JobDetailPage` — ~890L
- `features/submit/hooks/use-submit-wizard.ts:37` `useSubmitWizard` — ~740L
- `components/sidebar.tsx:58` `Sidebar` — ~354L
- `components/sidebar.tsx:412` `JobRow` — ~300L
- `features/optimizations/components/DataTab.tsx:39` `DataTab` — ~552L

### Current coupling (imports that cross intended feature boundaries)

- `app/page.tsx` imports `@/components/analytics-charts`, `@/components/analytics-sections`, `@/components/analytics-tables` — these should live in `features/dashboard/components/`
- `app/page.tsx` imports `@/components/excel-filter` — this is a generic table utility, should be `shared/ui/excel-filter`
- `app/compare/page.tsx` defines inline formatters (`fmt`, `fmtImprovement`, `fmtElapsed`, `ScoreCard`) — should be `features/compare/lib/`

### Hardcoded strings / magic numbers

- DSPy module keys `"predict"` / `"cot"` scattered in `ModelStep.tsx:68-69`, `SummaryStep.tsx:144`, `use-submit-wizard.ts:55`
- Optimizer keys `"miprov2"` / `"gepa"` scattered in same files
- `PAGE_SIZE = 20` defined in `features/dashboard/constants.ts` AND redeclared in `components/sidebar.tsx:56`
- `process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"` duplicated in `app/page.tsx:271`, `app/optimizations/[id]/page.tsx:195`
- `GET_CACHE_MS = 2000` in `lib/api.ts:31`

### `'use client'` audit

- 64 files with `"use client"` directive total
- Necessary: all app pages, submit wizard subtree, tutorial overlay, providers, stateful components
- Candidates to remove (pure JSX, no hooks): `features/dashboard/lib/status-badges.tsx`
- Candidates for deeper push: `ConfigTab`, `CodeTab`, `OverviewTab`, `StageInfoModal` are presentational and could be server-static if their parent were

### Dead / stale (confirmed, ready to delete)

- `frontend/src/hooks/use-tutorial.ts` (270L) — zero imports; superseded by `useTutorialContext()` in the provider
- `frontend/src/components/ui/textarea.tsx` (20L) — zero imports; scaffolded shadcn component, not used
- 7 unused npm packages in `frontend/package.json`:
  - `@codemirror/theme-one-dark`
  - `@fontsource-variable/heebo`, `/inter`, `/jetbrains-mono`
  - `exceljs`
  - `geist`
  - `xlsx`

## Backend (`backend/core`)

### Files > 300 lines

| Lines | File | One-liner |
|---|---|---|
| 922 | `core/api/routers/optimizations.py` | Lifecycle router: list, detail, cancel, artifact, logs |
| 697 | `core/worker/engine.py` | `BackgroundWorker` (threads, cancel events, mp subprocess) |
| 627 | `core/service_gateway/core.py` | `DspyService.run()` + `run_grid_search()` orchestration |
| 519 | `core/storage/remote.py` | PostgreSQL JobStore + SQLAlchemy models |
| 436 | `core/api/routers/serve.py` | Inference endpoints (sync + SSE streaming) |
| 386 | `core/api/routers/analytics.py` | Aggregation stats |
| 349 | `core/service_gateway/optimizers.py` | Optimizer factories + validation + compile/eval |
| 313 | `core/service_gateway/progress.py` | tqdm → JobStore progress bridge |
| 304 | `core/api/routers/_helpers.py` | Shared: quota, program cache, summary builder |
| 292 | `core/api/app.py` | FastAPI factory + lifespan + CORS + exception handlers |

### Functions > 80 lines

- `optimizations.py:80` `create_optimizations_router()` — 843L (closure holds all endpoints)
- `optimizations.py:212` `get_job()` — 109L
- `optimizations.py:342` `get_job_dataset()` — 88L
- `optimizations.py:430` `evaluate_examples()` — 141L
- `serve.py:24` `create_serve_router()` — 413L
- `serve.py:139` `serve_program_stream()` — 126L
- `serve.py:339` `serve_pair_program_stream()` — 98L
- `analytics.py:27` `create_analytics_router()` — 360L
- `analytics.py:41` `get_analytics_summary()` — 137L
- `worker/engine.py:200` `_process_job()` — 214L
- `worker/engine.py:215` `_check_cancel()` — 199L (partially extracted already)
- `service_gateway/core.py:85` `DspyService.run()` — 197L
- `service_gateway/core.py:282` `DspyService.run_grid_search()` — 252L

### Pydantic audit

- **ConfigDict(strict=True)**: 0 models
- **frozen=True**: 0 models
- **StrEnum**: 0 (OptimizationStatus is `str, Enum` — convertible)
- **SecretStr**: 0 (API keys travel in plain dicts under `extra`)
- **`@model_validator`**: present on `ColumnMapping`, `SplitFractions`, `_OptimizationRequestBase`, `RunRequest`, `GridSearchRequest`, `ServeRequest` — good

### Request/response schema separation violations

These models are used as **both** request body AND response body — flag for separation:
- `ColumnMapping` — used in `RunRequest`, `GridSearchRequest`, and in `_JobResponseBase`, `OptimizationStatusResponse`
- `ModelConfig` — used in `RunRequest`, `GridSearchRequest`, `ServeRequest`, and in status response
- `SplitFractions` — request AND response

### Env var surface (11 sites — consolidation target for `core/config.py`)

| Var | File |
|---|---|
| `REMOTE_DB_URL` | `core/storage/__init__.py:23` |
| `ALLOWED_ORIGINS` | `core/api/app.py:112` |
| `WORKER_STALE_THRESHOLD` | `core/api/app.py:201` |
| `CANCEL_POLL_INTERVAL` | `core/worker/engine.py:67` |
| `JOB_RUN_START_METHOD` | `core/worker/engine.py:88` |
| `WORKER_CONCURRENCY` | `core/worker/engine.py:667` |
| `WORKER_POLL_INTERVAL` | `core/worker/engine.py:668` |
| `COMMS_WEBHOOK_URL` | `core/notifications/comms.py:20` |
| `COMMS_CHANNEL` | `core/notifications/comms.py:21` |
| `FRONTEND_URL` | `core/notifications/notifier.py:15` |
| (dynamic API-key env var) | `core/api/model_catalog.py:127` |

### Exception handling

- 68 `HTTPException` sites + 24 `ServiceError` sites
- Central handler already registered in `core/api/app.py:136-146` ✓ (returns `{"error", "detail"}`)
- No `AppError` base hierarchy — error types are distinguished by `HTTPException(status_code=N)` directly

### JobStore interface — CQRS split candidate

- **Reads (9)**: `get_job`, `job_exists`, `get_progress_events`, `get_progress_count`, `get_logs`, `get_log_count`, `list_jobs`, `count_jobs`, `recover_pending_jobs`
- **Writes (7)**: `create_job`, `update_job`, `delete_job`, `record_progress`, `append_log`, `set_payload_overview`, `recover_orphaned_jobs`

### Async/sync

- Sync routers for DB reads ✓
- Async routers only for SSE streaming ✓
- JobStore protocol fully sync ✓
- BackgroundWorker uses threading + multiprocessing ✓
- Service gateway fully sync (CPU-bound) ✓

No obvious wrong choices.

### Dead code (backend)

None. All 52 `core/` modules are reachable. No orphaned public functions. No commented-out blocks.

## Contracts (frontend ↔ backend)

### Orphans (backend schemas with no frontend consumer)

- `ProgramArtifactResponse` (`optimizations.py:120`) — declared but not registered as response_model
- `AnalyticsSummaryResponse`, `OptimizerStatsResponse`, `ModelStatsResponse` (`analytics.py`) — **backend defines these, frontend never imports them** → the analytics tab is consuming `/optimizations` and aggregating client-side

### Misnamed pairs (aliases accepted, rename candidates)

- `RunResponse` (backend) ↔ `RunResult` (frontend)
- `GridSearchResponse` (backend) ↔ `GridSearchResult` (frontend)
- `JobLogEntry` (backend) ↔ `OptimizationLogEntry` (frontend)

### Field drift

- `OptimizationLogEntry.pair_index?: number | null` (frontend) — backend `JobLogEntry` has no such field; frontend over-specifies
- `RunResult.split_counts` (frontend inline `{train, val, test}`) should reuse `SplitCounts` interface
- `RunResponse` (backend) has `optimization_metadata: Dict[str, Any]` and `details: Dict[str, Any]` that the frontend `RunResult` does not declare — data loss on the wire

### Zero camelCase leaks

Both sides cleanly use snake_case.

## Summary

**Frontend — Phase 2 targets (priority order)**

1. Delete dead files: `hooks/use-tutorial.ts`, `components/ui/textarea.tsx`
2. Uninstall 7 unused npm packages
3. Move `analytics-charts.tsx`, `analytics-sections.tsx`, `analytics-tables.tsx`, `analytics-empty.tsx` → `features/dashboard/components/`
4. Move `excel-filter.tsx` → `shared/ui/excel-filter.tsx`
5. Extract `JobRow` from `components/sidebar.tsx:412` → `features/sidebar/components/JobRow.tsx`
6. Fix `PAGE_SIZE` duplication (sidebar imports from dashboard constants)
7. Hoist API URL constant from two pages to `lib/api.ts` (or `shared/constants/`)
8. Decompose `app/page.tsx` (2164L) into `features/dashboard/` with orchestrator + sub-panels
9. Hardcoded module/optimizer names → `features/submit/constants/dspy.ts` as typed const objects
10. Frontend type alignment — rename `RunResult → RunResponse`, `GridSearchResult → GridSearchResponse`, `OptimizationLogEntry → JobLogEntry` (OR keep aliases and document) — decision point

**Backend — Phase 3 targets (priority order)**

1. `core/config.py` — consolidate 11 env var sites into Pydantic `BaseSettings`
2. `AppError` hierarchy + middleware handler — distinguish `NotFoundError`/`ValidationError`/`ConflictError` classes, delete 68 raw `HTTPException` sites where domain knows the category
3. Pydantic hardening: `ConfigDict(strict=True, frozen=True)` on request models, `StrEnum` for `OptimizationStatus`, `SecretStr` for API keys in `ModelConfig.extra`
4. Split `ColumnMapping`/`ModelConfig`/`SplitFractions` into request/response variants (the response variant can be frozen+strict; the request variant stays permissive for ergonomic inputs)
5. Decompose `optimizations.py` (922L) — split into reads router + writes router, or by domain sub-action (lifecycle / artifact / logs / dataset)
6. Extract `get_job()` 109L, `evaluate_examples()` 141L from `optimizations.py` into service-layer methods
7. JobStore CQRS split: `JobQueryStore` (reads) + `JobWriteStore` (writes) at the Protocol level; `RemoteDBJobStore` implements both
8. Decompose `DspyService.run()` 197L and `run_grid_search()` 252L — per-stage helper methods
