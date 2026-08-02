#!/usr/bin/env bash
# Проверка перед пушем: не утекли ли секреты в рабочее дерево или в историю.
# Запускать до `git push`, особенно до первого.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0

echo "--- 1. .env и secrets/ должны игнорироваться ---"
for p in .env secrets/google_service_account.json; do
  if [ -e "$p" ]; then
    if git check-ignore -q "$p"; then
      echo "  ok: $p игнорируется"
    else
      echo "  ПРОВАЛ: $p НЕ игнорируется"
      fail=1
    fi
  fi
done

echo "--- 2. Секретных файлов не должно быть в истории ---"
hits=$(git log --all --pretty=format: --name-only \
       | sort -u \
       | grep -E '(^|/)\.env$|^secrets/' || true)
if [ -n "$hits" ]; then
  echo "  ПРОВАЛ: в истории найдены файлы:"
  echo "$hits" | sed 's/^/    /'
  fail=1
else
  echo "  ok: ни .env, ни secrets/ в коммитах не встречаются"
fi

echo "--- 3. Поиск характерных секретов в отслеживаемых файлах ---"
# Приватный ключ, bot-токен Telegram, client_secret Авито (40 символов base62).
patterns='BEGIN [A-Z ]*PRIVATE KEY|[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}'
found=$(git grep -nIE "$patterns" -- . ':!scripts/audit_secrets.sh' || true)
if [ -n "$found" ]; then
  echo "  ПРОВАЛ: похоже на секрет в отслеживаемых файлах:"
  echo "$found" | sed 's/^/    /'
  fail=1
else
  echo "  ok: явных секретов не найдено"
fi

if [ "$fail" -ne 0 ]; then
  echo "--- НЕ ПУШИТЬ, пока не устранено ---"
  exit 1
fi
echo "--- всё чисто ---"
