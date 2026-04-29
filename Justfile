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

update-scalar:
    bash scripts/update_scalar.sh

# Verify the generated i18n artefacts are in sync with i18n/locales/he.json.
# Snapshots the artefacts, regenerates them, and fails if the regenerator
# produced any new bytes — i.e. someone hand-edited the canonical catalog
# without running scripts/generate_i18n.py. Snapshot/restore semantics keep
# the working tree clean even when the check fails.
check-i18n:
    #!/usr/bin/env bash
    set -euo pipefail
    files=(i18n/keys.json frontend/src/shared/lib/generated/i18n-catalog.ts backend/core/i18n_keys.py backend/core/i18n_locales/he.json)
    snap=$(mktemp -d)
    trap 'rm -rf "$snap"' EXIT
    for f in "${files[@]}"; do cp "$f" "$snap/$(basename "$f")"; done
    python3 scripts/generate_i18n.py
    drift=0
    for f in "${files[@]}"; do
        diff -q "$snap/$(basename "$f")" "$f" >/dev/null || drift=1
    done
    if [ "$drift" -ne 0 ]; then
        echo "i18n drift: regenerated artefacts differ. Run 'python3 scripts/generate_i18n.py' and commit the result."
        exit 1
    fi

info:
    @echo "Project: Skynet (DSPy-as-a-Service)"
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
