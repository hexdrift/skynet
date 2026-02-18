# DSPy as a Service

FastAPI service that runs DSPy optimization jobs asynchronously over HTTP. Clients submit datasets + signature/metric code, then poll job status/logs/artifacts.

This README is for service operators (deployment, configuration, extension). If you only consume the API, start with `usage_guide/README.md`.

## Contents
- Prerequisites
- Install and Run
- Architecture
- Configuration
- Built-in Resolution and Extensibility
- Request Payload Contract
- API Reference
- Artifacts and Logs
- Operational Notes
- Client Usage Guide

## Prerequisites
- Python 3.10+ (3.11 recommended)
- DSPy-compatible dependencies (`dspy`, `litellm`, etc.)
- Provider credentials in environment variables (for example `OPENAI_API_KEY`)

## Install and Run
### Option A: `uv` (recommended)
```bash
# 1) create environment
uv venv .venv
source .venv/bin/activate

# 2) install service + dev extras
uv pip install -e '.[dev]'

# 3) provider credentials
export OPENAI_API_KEY=sk-...

# 4) run API
uv run python main.py
```

### Option B: `venv` + `pip`
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
export OPENAI_API_KEY=sk-...
python main.py
```

Server defaults to `http://0.0.0.0:8000`.

Equivalent direct Uvicorn command:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker
`docker-compose.yml` is a single-container deployment (API + in-process background workers):
```bash
docker compose up --build
```

## Architecture
Current runtime architecture is:

```text
FastAPI (/run, /jobs/*, /health, /queue)
        |
        v
BackgroundWorker (thread pool, in-process queue)
        |
        v
Job subprocess (per running job, cancellable)
        |
        v
DspyService (validate + compile + evaluate inside subprocess)
        |
        v
JobStore backend (default: LocalDBJobStore, optional: RemoteDBJobStore scaffold)
```

Package structure:
```text
core/
├── __init__.py              — public API re-exports
├── constants.py             — shared constant keys
├── exceptions.py            — service error types
├── models.py                — Pydantic request/response models
├── api/                     — HTTP layer
│   ├── app.py               — FastAPI routes and lifecycle
│   └── converters.py        — job data → response converters
├── storage/                 — persistence layer
│   ├── __init__.py          — backend selection (`JOB_STORE_BACKEND`)
│   ├── base.py              — JobStore protocol
│   ├── local.py             — LocalDBJobStore (SQLite, default)
│   └── remote.py            — RemoteDBJobStore scaffold (implement TODO stubs)
├── worker/                  — background job processing
│   ├── engine.py            — threaded worker (WORKER_CONCURRENCY, WORKER_POLL_INTERVAL)
│   └── log_handler.py       — per-job log capture handler
├── registry/                — module and optimizer resolution
│   ├── core.py              — ServiceRegistry
│   └── resolvers.py         — built-in aliases + dotted path resolution
└── service_gateway/         — DSPy orchestration pipeline
    ├── core.py              — DspyService (validate + compile + evaluate)
    ├── artifacts.py          — program serialization
    ├── data.py              — dataset loading, splitting, column mapping
    ├── language_models.py   — LLM construction from model config
    ├── optimizers.py        — optimizer instantiation and compilation
    └── progress.py          — tqdm progress capture
```

Important implementation status:
- `RemoteDBJobStore` methods are scaffolds with `TODO` stubs. See `core/storage/remote.py` for the full DB schema and implementation guide.

## Configuration
Environment variables used by runtime:
- `OPENAI_API_KEY` / provider-specific keys: required by your selected model provider
- `JOB_STORE_BACKEND`: `local` (default) or `remote`
- `LOCAL_DB_PATH`: SQLite DB path when `JOB_STORE_BACKEND=local` (default `dspy_jobs.db`)
- `REMOTE_DB_URL`: required when `JOB_STORE_BACKEND=remote`
- `REMOTE_DB_API_KEY`: auth token for your remote DB API (optional, backend-specific)
- `WORKER_CONCURRENCY`: number of worker threads, default `2`
- `WORKER_POLL_INTERVAL`: queue poll interval in seconds, default `2.0`
- `CANCEL_POLL_INTERVAL`: cancellation poll interval while a run is executing, default `1.0`
- `JOB_RUN_START_METHOD`: multiprocessing start method for per-job subprocesses (`fork` default)
- `WORKER_STALE_THRESHOLD`: max seconds of no worker activity before health check flags it, default `600`

## Built-in Resolution and Extensibility
Built-in aliases (see `core/registry/resolvers.py`):
- Modules:
  - `predict` -> `dspy.Predict`
  - `cot` -> `dspy.modules.ChainOfThought` (fallback `dspy.ChainOfThought`)
- Optimizers:
  - `miprov2` -> `dspy.teleprompt.MIPROv2`
  - `gepa` -> `dspy.teleprompt.GEPA`

You can also reference dotted `dspy.*` paths directly in payloads.

For custom factories, register with `ServiceRegistry` before app creation in `main.py`:
```python
from core import ServiceRegistry, create_app

registry = ServiceRegistry()
registry.register_module("my_module", my_module_factory)
registry.register_optimizer("my_optimizer", my_optimizer_factory)

app = create_app(registry=registry)
```

## Request Payload Contract
`POST /run` expects:
1. `module_name`: alias or dotted path
2. `signature_code`: Python code defining exactly one `dspy.Signature` subclass
3. `metric_code`: Python code defining a callable metric (`metric(...)` preferred)
4. `optimizer_name`: alias or dotted path
5. `dataset`: non-empty list of row dictionaries
6. `column_mapping`: object with:
   - `inputs`: signature input field -> dataset column
   - `outputs`: signature output field -> dataset column
7. `model_config`: base model configuration
8. Optional:
   - `module_kwargs`, `optimizer_kwargs`, `compile_kwargs`
   - `reflection_model_config` (required by GEPA unless `reflection_lm` passed)
   - `prompt_model_config` and `task_model_config` (for MiPROv2 overrides)
   - `split_fractions` (`train`, `val`, `test`, sum must be `1.0`)
   - `shuffle`, `seed`

Validation behavior:
- Schema/shape issues -> HTTP `422`
- Unsupported optimizer kwargs / semantic issues -> HTTP `400`

Security note:
- `signature_code` and `metric_code` are executed with `exec(...)`. Treat this service as trusted-input unless you sandbox/guard execution externally.

## API Reference
### `POST /run`
Validates payload, creates job record, enqueues background processing. Returns `201`.

Response:
```json
{
  "job_id": "uuid",
  "status": "pending"
}
```

### `GET /jobs`
List all jobs with optional filtering and pagination.

Query parameters:
- `status`: filter by job status
- `username`: filter by username
- `limit`: max results (1-500, default 50)
- `offset`: skip N results (default 0)

### `GET /jobs/{job_id}`
Detailed job view: status, timestamps, latest metrics, full progress events, logs, and `result` on success.

Statuses:
- `pending`
- `validating`
- `running`
- `success`
- `failed`
- `cancelled`

### `GET /jobs/{job_id}/summary`
Lightweight dashboard-friendly summary with payload overview + latest metrics.

### `GET /jobs/{job_id}/logs`
Chronological list of captured log entries.

### `GET /jobs/{job_id}/artifact`
Returns serialized artifact only after success.
- `200`: artifact available
- `409`: job still running
- `404`: job missing or no artifact produced

### `POST /jobs/{job_id}/cancel`
Cancel a pending or running job.
- `200`: cancelled successfully
- `409`: job already in a terminal state
- `404`: job not found

### `DELETE /jobs/{job_id}`
Delete a completed, failed, or cancelled job and all its data.
- `200`: deleted successfully
- `409`: job still active (cancel it first)
- `404`: job not found

### `GET /queue`
Queue and worker status snapshot:
```json
{
  "pending_jobs": 0,
  "active_jobs": 1,
  "worker_threads": 2,
  "workers_alive": true
}
```

### `GET /health`
Basic health + registered assets snapshot:
```json
{
  "status": "ok",
  "registered_assets": {
    "modules": [],
    "metrics": [],
    "optimizers": []
  }
}
```

## Artifacts and Logs
Artifact payload (`program_artifact`) includes:
- `metadata`: parsed `metadata.json`
- `program_pickle_base64`: base64-encoded `program.pkl`
- `optimized_prompt`: extracted prompt/demo summary from first predictor (when available)

Current behavior:
- Artifacts are generated in a temporary directory and returned inline.
- Temporary files are deleted after packaging.
- `program_artifact.path` is currently `null`.

Materialize artifact helper:
```python
import base64
import json
from pathlib import Path

def materialize_artifact(bundle, destination):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "metadata.json").write_text(json.dumps(bundle["metadata"], indent=2))
    (dest / "program.pkl").write_bytes(base64.b64decode(bundle["program_pickle_base64"]))
    return dest
```

Logs:
- DSPy `INFO` logs are captured per job.
- Logs are available via `/jobs/{id}/logs` and embedded in successful `result.run_log`.

## Operational Notes
- CORS is currently open (`allow_origins=["*"]`).
- No built-in auth/rate limiting in this repo.
- On startup, orphaned jobs (stuck in `running`/`validating` from a previous crash) are automatically marked as `failed`.

## Reliability Contract
- Cancelled jobs are deleted; `GET /jobs/{id}` returns `404` after cancellation.
- Pending jobs are recovered from storage and re-queued on startup.
- Running jobs execute inside per-job subprocesses and are terminated on cancellation.
- Reliability guarantees are validated for Linux/OpenShift deployments (`fork` start method).

## Client Usage Guide
See `usage_guide/README.md` for notebook examples and end-to-end client flow.

Quick setup for guide environment:
```bash
cd usage_guide
uv venv .venv
source .venv/bin/activate
uv pip install -r pyproject.toml
```
