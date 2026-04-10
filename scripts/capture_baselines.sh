#!/usr/bin/env bash
# Phase 0 baseline capture + Phase 5 regression gate.
#
# Captures a deterministic snapshot of the current backend API contract
# (OpenAPI + response shapes) and frontend build output to
# /tmp/skynet-baselines/. Intended as a regression gate for the
# multi-phase refactor driven from the branch refactor/submit-slice-pilot.
#
# Usage:
#   scripts/capture_baselines.sh              # capture fresh baseline
#   scripts/capture_baselines.sh --verify     # diff current state vs baseline
#
# Prereqs:
#   - backend running at http://localhost:8000 (python backend/main.py)
#   - frontend dev server at http://localhost:3001 (npm run dev in frontend/)
#   - .venv/bin/python available at repo root
#
# Screenshots are captured separately via Playwright MCP during the
# refactor. This script covers the non-visual gate.
set -euo pipefail

DIR="${BASELINE_DIR:-/tmp/skynet-baselines}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-capture}"

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
PY="${REPO}/.venv/bin/python"

mkdir -p "$DIR" "$DIR/api-responses" "$DIR/logs"

capture() {
  echo "== Phase 0: capturing baselines to $DIR =="

  echo "-- git state"
  (cd "$REPO" && {
    git rev-parse HEAD
    git branch --show-current
    git log --oneline -10
  }) > "$DIR/git-state.txt"

  echo "-- line counts"
  {
    echo "frontend/src:"
    find "$REPO/frontend/src" -type f \( -name '*.ts' -o -name '*.tsx' \) -print0 | xargs -0 wc -l | tail -1
    echo "backend/core:"
    find "$REPO/backend/core" -type f -name '*.py' -print0 | xargs -0 wc -l | tail -1
  } > "$DIR/line-counts.txt"

  echo "-- frontend build"
  (cd "$REPO/frontend" && npm run build) > "$DIR/frontend-build.log" 2>&1 || {
    echo "FAIL: npm run build exited non-zero" >&2
    tail -30 "$DIR/frontend-build.log" >&2
    exit 1
  }

  echo "-- backend unit tests"
  (cd "$REPO" && "$PY" -m pytest backend/tests/unit -v) > "$DIR/backend-unit-tests.log" 2>&1 || {
    echo "FAIL: pytest exited non-zero" >&2
    tail -30 "$DIR/backend-unit-tests.log" >&2
    exit 1
  }

  echo "-- openapi snapshot"
  curl -sS "$BACKEND_URL/openapi.json" | "$PY" -m json.tool --sort-keys > "$DIR/openapi.json"
  shasum -a 256 "$DIR/openapi.json" | cut -d' ' -f1 > "$DIR/openapi.sha256"

  echo "-- enumerate endpoints"
  "$PY" - <<PY > "$DIR/endpoints.txt"
import json
with open("$DIR/openapi.json") as f:
    spec = json.load(f)
for path, methods in sorted(spec.get("paths", {}).items()):
    for m in sorted(methods):
        if m in ("get", "post", "put", "delete", "patch"):
            print(f"{m.upper():6} {path}")
PY

  echo "-- fetch a sample optimization id"
  curl -sS "$BACKEND_URL/optimizations?limit=1" \
    | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(d['items'][0]['optimization_id']) if d.get('items') else ''" \
    > "$DIR/.sample_id"
  SID="$(cat "$DIR/.sample_id")"

  echo "-- capture GET endpoint responses"
  > "$DIR/api-responses/.index"
  for ep in /health /queue /analytics/summary /analytics/optimizers /analytics/models /models /optimizations /optimizations/sidebar /templates; do
    fn="$DIR/api-responses${ep//\//_}.json"
    code=$(curl -sS "$BACKEND_URL$ep" -o "$fn" -w "%{http_code}")
    echo "$code $ep" >> "$DIR/api-responses/.index"
  done
  if [ -n "$SID" ]; then
    for ep in "/optimizations/$SID" "/optimizations/$SID/summary" "/optimizations/$SID/logs" "/optimizations/$SID/payload" "/optimizations/$SID/artifact" "/serve/$SID/info"; do
      fn="$DIR/api-responses${ep//\//_}.json"
      code=$(curl -sS "$BACKEND_URL$ep" -o "$fn" -w "%{http_code}")
      echo "$code $ep" >> "$DIR/api-responses/.index"
    done
  fi

  echo "-- compute response-shape fingerprints"
  "$PY" - <<PY > "$DIR/api-shapes.json"
import json
from pathlib import Path

def shape(obj, depth=0, max_depth=5):
    if depth > max_depth:
        return "<deep>"
    if obj is None: return "null"
    if isinstance(obj, bool): return "bool"
    if isinstance(obj, int): return "int"
    if isinstance(obj, float): return "float"
    if isinstance(obj, str): return "string"
    if isinstance(obj, list):
        return ["<empty>"] if not obj else [shape(obj[0], depth+1, max_depth)]
    if isinstance(obj, dict):
        return {k: shape(v, depth+1, max_depth) for k, v in sorted(obj.items())}
    return type(obj).__name__

sid = Path("$DIR/.sample_id").read_text().strip()
out = {}
root = Path("$DIR")
for p in sorted(root.glob("api-responses_*.json")):
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        out[p.name] = f"ERROR: {e}"
        continue
    name = p.stem[len("api-responses_"):] if p.stem.startswith("api-responses_") else p.stem
    if sid:
        name = name.replace(sid, "ID")
    endpoint = "/" + name.replace("_", "/")
    out[endpoint] = shape(data)
print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
PY

  shasum -a 256 "$DIR/api-shapes.json" | cut -d' ' -f1 > "$DIR/api-shapes.sha256"

  echo "== capture complete =="
  echo "  openapi.sha256:    $(cat "$DIR/openapi.sha256")"
  echo "  api-shapes.sha256: $(cat "$DIR/api-shapes.sha256")"
}

verify() {
  echo "== Phase 5 gate: verifying against $DIR =="
  [ -f "$DIR/openapi.sha256" ] || { echo "no baseline at $DIR — run without --verify first"; exit 2; }

  FAIL=0

  echo "-- frontend build"
  (cd "$REPO/frontend" && npm run build) > "$DIR/logs/build-current.log" 2>&1 || {
    echo "FAIL: build exited non-zero"
    FAIL=1
  }
  base_err=$(grep -cE 'Error|✖' "$DIR/frontend-build.log" || true)
  cur_err=$(grep -cE 'Error|✖' "$DIR/logs/build-current.log" || true)
  if [ "$base_err" != "$cur_err" ]; then
    echo "FAIL: build error count drift (baseline=$base_err current=$cur_err)"
    FAIL=1
  fi

  echo "-- backend unit tests"
  (cd "$REPO" && "$PY" -m pytest backend/tests/unit -q) > "$DIR/logs/tests-current.log" 2>&1 || FAIL=1
  base_pass=$(grep -oE '[0-9]+ passed' "$DIR/backend-unit-tests.log" | head -1)
  cur_pass=$(grep -oE '[0-9]+ passed' "$DIR/logs/tests-current.log" | head -1)
  if [ "$base_pass" != "$cur_pass" ]; then
    echo "FAIL: pytest count drift (baseline=$base_pass current=$cur_pass)"
    FAIL=1
  fi

  echo "-- openapi drift"
  curl -sS "$BACKEND_URL/openapi.json" | "$PY" -m json.tool --sort-keys > "$DIR/logs/openapi-current.json"
  cur_hash=$(shasum -a 256 "$DIR/logs/openapi-current.json" | cut -d' ' -f1)
  base_hash=$(cat "$DIR/openapi.sha256")
  if [ "$base_hash" != "$cur_hash" ]; then
    echo "FAIL: openapi drift"
    echo "  baseline: $base_hash"
    echo "  current:  $cur_hash"
    FAIL=1
  fi

  echo "-- response shape drift"
  SID="$(cat "$DIR/.sample_id")"
  rm -f "$DIR/logs/api-current"/* 2>/dev/null || true
  mkdir -p "$DIR/logs/api-current"
  for ep in /health /queue /analytics/summary /analytics/optimizers /analytics/models /models /optimizations /optimizations/sidebar /templates "/optimizations/$SID" "/optimizations/$SID/summary" "/optimizations/$SID/logs" "/optimizations/$SID/payload" "/optimizations/$SID/artifact" "/serve/$SID/info"; do
    fn="$DIR/logs/api-current${ep//\//_}.json"
    curl -sS "$BACKEND_URL$ep" -o "$fn" 2>/dev/null
  done
  "$PY" - <<PY > "$DIR/logs/api-shapes-current.json"
import json
from pathlib import Path

def shape(obj, depth=0, max_depth=5):
    if depth > max_depth: return "<deep>"
    if obj is None: return "null"
    if isinstance(obj, bool): return "bool"
    if isinstance(obj, int): return "int"
    if isinstance(obj, float): return "float"
    if isinstance(obj, str): return "string"
    if isinstance(obj, list):
        return ["<empty>"] if not obj else [shape(obj[0], depth+1, max_depth)]
    if isinstance(obj, dict):
        return {k: shape(v, depth+1, max_depth) for k, v in sorted(obj.items())}
    return type(obj).__name__

sid = Path("$DIR/.sample_id").read_text().strip()
out = {}
root = Path("$DIR/logs")
for p in sorted(root.glob("api-current*.json")):
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        out[p.name] = f"ERROR: {e}"
        continue
    name = p.stem
    if name.startswith("api-current_"):
        name = name[len("api-current_"):]
    if sid:
        name = name.replace(sid, "ID")
    endpoint = "/" + name.replace("_", "/")
    out[endpoint] = shape(data)
print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
PY
  cur_shape_hash=$(shasum -a 256 "$DIR/logs/api-shapes-current.json" | cut -d' ' -f1)
  base_shape_hash=$(cat "$DIR/api-shapes.sha256")
  if [ "$base_shape_hash" != "$cur_shape_hash" ]; then
    echo "FAIL: response shape drift"
    diff "$DIR/api-shapes.json" "$DIR/logs/api-shapes-current.json" || true
    FAIL=1
  fi

  if [ "$FAIL" -eq 0 ]; then
    echo "== gate PASSED =="
    exit 0
  else
    echo "== gate FAILED =="
    exit 1
  fi
}

case "$MODE" in
  --verify|verify) verify ;;
  capture|*) capture ;;
esac
