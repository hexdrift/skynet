# Skynet Justfile — task runner for dev, test, and agent workflows
# Usage: just <recipe> [args]
# Requires: https://github.com/casey/just

default:
    @just --list

backend:
    cd backend && uv run python main.py

frontend:
    cd frontend && npm run dev

# Start both (backend in background, frontend in foreground)
dev:
    cd backend && uv run python main.py &
    cd frontend && npm run dev

test-unit:
    cd backend && uv run --extra dev pytest core/ tests/unit/ -v

# Requires running server + OPENAI_API_KEY
test-integration:
    cd backend && uv run --extra dev pytest tests/test_llm_integration.py -v

# Frontend type check via build
test-frontend:
    cd frontend && npm run build

test: test-unit test-frontend

lint-backend:
    cd backend && uv run ruff check .

lint-frontend:
    cd frontend && npm run lint

lint: lint-backend lint-frontend

format:
    cd backend && uv run ruff format .

fix:
    cd backend && uv run ruff check --fix .

# Verify the generated i18n artefacts are in sync with i18n/locales/he.json.
# Delegates to the script's built-in --check mode (renders artefacts in
# memory and exits non-zero on drift, without touching the working tree).
check-i18n:
    python3 scripts/generate_i18n.py --check

info:
    @echo "Project: Skynet"
    @echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'not a git repo')"
    @echo "Python: $(python3 --version 2>/dev/null || echo 'not installed')"
    @echo "Node: $(node --version 2>/dev/null || echo 'not installed')"

cli:
    claude

plan task:
    claude -p "/scout-and-plan {{task}}"

implement task:
    claude -p "/implement {{task}}"

review:
    claude -p "/review"
