#!/usr/bin/env bash
# Daily dashboard data export — chain after daily-news pipeline.
# This script does NOT deploy; it only refreshes JSON snapshots locally.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found, skipping dashboard export" >&2
  exit 0
fi

uv run --with-requirements requirements.txt --python python3 \
  python dashboard_export.py \
  --output "$REPO_ROOT/web/src/data"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] dashboard JSON refreshed"
