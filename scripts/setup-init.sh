#!/usr/bin/env bash
# Setup Init Script — runs on first-time codebase installation
# Triggered by: claude --init, pi --init, or just install
#
# Customize this for your codebase. Add your specific setup steps below.
# Results are logged to logs/setup-init.log for the agent to read.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/setup-init.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Setup Init Started ==="

# --- Detect project type ---
# This is a full-stack project with Next.js frontend and FastAPI backend

# Frontend setup (Next.js)
if [ -d "$PROJECT_ROOT/frontend" ] && [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
  log "Setting up Next.js frontend..."
  cd "$PROJECT_ROOT/frontend"
  npm install 2>&1 | tee -a "$LOG_FILE"
  cd "$PROJECT_ROOT"
fi

# Backend setup (FastAPI + Python)
if [ -d "$PROJECT_ROOT/backend" ]; then
  log "Setting up FastAPI backend..."
  cd "$PROJECT_ROOT/backend"
  
  if [ -f "pyproject.toml" ]; then
    log "Running uv sync for backend..."
    uv sync 2>&1 | tee -a "$LOG_FILE" || pip install -e ".[dev]" 2>&1 | tee -a "$LOG_FILE"
  elif [ -f "requirements.txt" ]; then
    log "Running pip install for backend..."
    pip install -r requirements.txt 2>&1 | tee -a "$LOG_FILE"
  fi
  
  cd "$PROJECT_ROOT"
fi

# Root level dependencies (if any)
if [ -f "package.json" ]; then
  log "Installing root package.json dependencies..."
  npm install 2>&1 | tee -a "$LOG_FILE"
fi

if [ -f "pyproject.toml" ] && [ ! -d "backend" ]; then
  log "Installing root Python dependencies..."
  uv sync 2>&1 | tee -a "$LOG_FILE" || pip install -e ".[dev]" 2>&1 | tee -a "$LOG_FILE"
fi

# --- Environment setup ---
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  log "Creating .env from .env.example"
  cp .env.example .env
  log "NOTE: Please update .env with your actual values"
fi

# --- Database setup (customize for your project) ---
# Uncomment and customize as needed:
# log "Running database migrations..."
# npx prisma migrate dev 2>&1 | tee -a "$LOG_FILE"
# python manage.py migrate 2>&1 | tee -a "$LOG_FILE"
# npx knex migrate:latest 2>&1 | tee -a "$LOG_FILE"

# --- Custom setup steps ---
# Add your project-specific setup here:
# log "Running custom setup..."

log "=== Setup Init Complete ==="
