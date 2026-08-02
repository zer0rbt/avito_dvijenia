#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
uvicorn web.app:app --host 0.0.0.0 --port "${WEB_PORT:-8000}"
