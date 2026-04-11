#!/usr/bin/env bash
# Refresh the bundled Scalar API reference assets for air-gapped use.
#
# Downloads @scalar/api-reference standalone.js and all referenced fonts
# from jsdelivr/fonts.scalar.com, places them under
# backend/core/api/static/scalar/, and rewrites font URLs in the bundle
# to point at /scalar-static/fonts/*.
#
# Usage:
#   scripts/update_scalar.sh             # latest version
#   scripts/update_scalar.sh 1.52.1      # pinned version
set -euo pipefail

VERSION="${1:-latest}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/backend/core/api/static/scalar"
FONTS_DIR="$DEST/fonts"

if [ "$VERSION" = "latest" ]; then
  VERSION=$(curl -sS "https://data.jsdelivr.com/v1/package/npm/@scalar/api-reference" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['tags']['latest'])")
fi

echo "== updating Scalar to @scalar/api-reference@$VERSION =="

mkdir -p "$DEST" "$FONTS_DIR"

echo "-- downloading standalone.js"
curl -sSL "https://cdn.jsdelivr.net/npm/@scalar/api-reference@$VERSION" \
  -o "$DEST/standalone.js"

echo "-- downloading fonts"
FONTS=(
  inter-cyrillic-ext inter-cyrillic inter-greek-ext inter-greek
  inter-latin-ext inter-latin inter-symbols inter-vietnamese
  mono-cyrillic-ext mono-cyrillic mono-greek
  mono-latin-ext mono-latin mono-vietnamese
)
for f in "${FONTS[@]}"; do
  curl -sSL -f "https://fonts.scalar.com/$f.woff2" -o "$FONTS_DIR/$f.woff2"
done

echo "-- rewriting font URLs in bundle"
python3 - "$DEST/standalone.js" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text()
count = src.count("https://fonts.scalar.com/")
if count == 0:
    print("  no external font references found — bundle already rewritten?", file=sys.stderr)
    sys.exit(1)
path.write_text(src.replace("https://fonts.scalar.com/", "/scalar-static/fonts/"))
print(f"  rewrote {count} font URLs")
PY

echo "-- verifying font rewrite"
# Only font URLs matter for offline use. Other URLs in the bundle (MDN
# links, GitHub, example.com, etc) are text data, not network requests.
if grep -q "fonts\.scalar\.com" "$DEST/standalone.js"; then
  echo "FAIL: bundle still references fonts.scalar.com" >&2
  exit 1
fi
local_count=$(grep -o "/scalar-static/fonts/" "$DEST/standalone.js" | wc -l | tr -d ' ')
if [ "${local_count:-0}" -lt 14 ]; then
  echo "FAIL: expected ≥14 local font refs, got $local_count" >&2
  exit 1
fi

BUNDLE_SIZE=$(wc -c < "$DEST/standalone.js" | tr -d ' ')
FONTS_SIZE=$(du -sh "$FONTS_DIR" | awk '{print $1}')
echo "== done =="
echo "  version:    $VERSION"
echo "  bundle:     $(numfmt --to=iec $BUNDLE_SIZE 2>/dev/null || echo "$BUNDLE_SIZE bytes")"
echo "  fonts dir:  $FONTS_SIZE"
echo "  commit with: git add $DEST && git commit -m 'chore: update scalar bundle to $VERSION'"
