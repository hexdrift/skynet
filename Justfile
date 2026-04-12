# Skynet Justfile — task runner for dev, test, and agent workflows
# Usage: just <recipe> [args]
# Requires: https://github.com/casey/just

default:
    @just --list

# --- Development ---

# Start backend (FastAPI + uvicorn)
backend:
    cd backend && uv run python main.py

# Start frontend (Next.js dev server)
frontend:
    cd frontend && npm run dev

# Start both (backend in background, frontend in foreground)
dev:
    cd backend && uv run python main.py &
    cd frontend && npm run dev

# --- Testing ---

# Run backend unit tests
test-unit:
    cd backend && uv run pytest tests/unit/ -v

# Run backend integration tests (requires running server + OPENAI_API_KEY)
test-integration:
    cd backend && uv run pytest tests/test_llm_integration.py -v

# Frontend type check via build
test-frontend:
    cd frontend && npm run build

# Run all tests
test: test-unit test-frontend

# --- Linting & Formatting ---

lint-backend:
    cd backend && uv run ruff check .

lint-frontend:
    cd frontend && npm run lint

lint: lint-backend lint-frontend

format:
    cd backend && uv run ruff format .

fix:
    cd backend && uv run ruff check --fix .

# --- Utilities ---

# Update bundled Scalar API docs
update-scalar:
    bash scripts/update_scalar.sh

# Show project info
info:
    @echo "Project: Skynet (DSPy-as-a-Service)"
    @echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'not a git repo')"
    @echo "Python: $(python3 --version 2>/dev/null || echo 'not installed')"
    @echo "Node: $(node --version 2>/dev/null || echo 'not installed')"

# --- Agent Workflows ---

# Start a Claude Code session
cli:
    claude

# Scout and plan a task
plan task:
    claude -p "/scout-and-plan {{task}}"

# Implement a task (scout -> plan -> build)
implement task:
    claude -p "/implement {{task}}"

# Code review + security audit
review:
    claude -p "/review"
