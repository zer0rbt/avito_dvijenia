#!/usr/bin/env bash
# Проверка стиля. С --fix — автопочинка того, что ruff умеет чинить сам.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate

if [ "${1:-}" = "--fix" ]; then
  ruff check . --fix
  ruff format .
else
  ruff check .
  ruff format --check .
fi
