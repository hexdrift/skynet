#!/usr/bin/env bash
# Setup Maintenance Script — runs for periodic codebase maintenance
# Triggered by: just maintain, or /maintain command
#
# Customize this for your codebase. Add maintenance steps below.
# Results are logged to logs/maintenance.log for the agent to read.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/maintenance.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Maintenance Started ==="

# --- Update dependencies ---
# Frontend dependencies (Next.js)
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
  log "Checking frontend dependencies..."
  cd frontend
  npm outdated 2>&1 | tee -a "$LOG_FILE" || true
  log "Updating frontend dependencies..."
  npm update 2>&1 | tee -a "$LOG_FILE"
  log "Running security audit on frontend..."
  npm audit 2>&1 | tee -a "$LOG_FILE" || true
  cd ..
fi

# Backend dependencies (FastAPI + Python)
if [ -d "backend" ]; then
  log "Checking backend dependencies..."
  cd backend
  
  if [ -f "pyproject.toml" ]; then
    log "Updating Python dependencies with uv..."
    uv sync --upgrade 2>&1 | tee -a "$LOG_FILE" || pip list --outdated 2>&1 | tee -a "$LOG_FILE"
  elif [ -f "requirements.txt" ]; then
    pip list --outdated 2>&1 | tee -a "$LOG_FILE" || true
  fi
  
  cd ..
fi

# Root level dependencies (if any)
if [ -f "package.json" ] && [ ! -d "frontend" ]; then
  log "Updating root package.json dependencies..."
  npm outdated 2>&1 | tee -a "$LOG_FILE" || true
  npm update 2>&1 | tee -a "$LOG_FILE"
fi

# --- Database maintenance ---
# Uncomment and customize as needed:
# log "Running database migrations..."
# npx prisma migrate deploy 2>&1 | tee -a "$LOG_FILE"
# log "Optimizing database..."
# sqlite3 db.sqlite3 "VACUUM;" 2>&1 | tee -a "$LOG_FILE"

# --- Artifact cleanup ---
log "Cleaning build artifacts..."
rm -rf dist/ build/ .cache/ tmp/ 2>/dev/null || true

# Frontend cleanup
if [ -d "frontend" ]; then
  log "Cleaning frontend artifacts..."
  rm -rf frontend/.next/ frontend/node_modules/.cache/ 2>/dev/null || true
fi

# Backend cleanup
if [ -d "backend" ]; then
  log "Cleaning backend artifacts..."
  find backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
  find backend -name "*.pyc" -delete 2>/dev/null || true
fi

# General Python cleanup
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# --- Custom maintenance ---
# Add your project-specific maintenance here:
# log "Running custom maintenance..."

log "=== Maintenance Complete ==="
