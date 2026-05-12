#!/bin/bash
set -euo pipefail

export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/andy/.local/bin

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"
mkdir -p data/logs

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

"$SCRIPT_DIR/ensure-rsshub.sh"

UV_BIN="${UV_BIN:-uv}"
PYTHON_BIN="${DAILY_NEWS_PYTHON:-python3}"
HOURS="${DAILY_NEWS_HOURS:-24}"

"$UV_BIN" run \
  --with-requirements requirements.txt \
  --python "$PYTHON_BIN" \
  python main.py \
  --hours "$HOURS" \
  --report-type daily

"$SCRIPT_DIR/generate-source-atlas.sh"
"$SCRIPT_DIR/export-dashboard-data.sh"
