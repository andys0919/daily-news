#!/usr/bin/env bash
# Daily dashboard data export — chain after daily-news pipeline.
# This script does NOT deploy; it refreshes JSON snapshots and rebuilds web/dist.
set -euo pipefail

export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/andy/.local/bin

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found, skipping dashboard export" >&2
  exit 0
fi

DB_PATH="${DASHBOARD_DB_PATH:-$REPO_ROOT/data/news.db}"
if [ ! -f "$DB_PATH" ]; then
  echo "dashboard DB not found: $DB_PATH" >&2
  exit 1
fi

uv run --with-requirements requirements.txt --python python3 \
  python dashboard_export.py \
  --db "$DB_PATH" \
  --output "$REPO_ROOT/web/src/data"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] dashboard JSON refreshed"

if [ "${DASHBOARD_SKIP_BUILD:-0}" = "1" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] dashboard build skipped"
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found, dashboard JSON refreshed but web/dist not rebuilt" >&2
  exit 1
fi

if [ ! -x "$REPO_ROOT/web/node_modules/.bin/astro" ]; then
  (cd "$REPO_ROOT/web" && npm install)
fi

(cd "$REPO_ROOT/web" && npm run build)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] dashboard web/dist rebuilt"
