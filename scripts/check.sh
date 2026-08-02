#!/usr/bin/env bash
# Гейт перед коммитом: стиль + тесты. Должен быть зелёным всегда.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "--- ruff ---"
bash scripts/lint.sh

echo "--- pytest ---"
bash scripts/test.sh

echo "--- ok ---"
