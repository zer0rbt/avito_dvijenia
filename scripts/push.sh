#!/usr/bin/env bash
# Push с ретраями: сеть WSL в этом окружении периодически не достукивается
# до github.com:443 (та же проблема, что с Google Sheets, см. B-013).
# Перед пушем — обязательный аудит секретов.
set -uo pipefail
cd "$(dirname "$0")/.."

bash scripts/audit_secrets.sh || exit 1

for attempt in 1 2 3 4 5; do
  echo "--- push, попытка $attempt ---"
  if git push -u origin master; then
    echo "--- push прошёл ---"
    exit 0
  fi
  echo "не вышло, ждём..."
  sleep 5
done

echo "--- push не прошёл за 5 попыток ---"
exit 1
