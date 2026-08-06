#!/usr/bin/env bash
# Разовая проверка: что уже настроено, а что держит первую публикацию.
# Значения переменных не печатаем — только заполнена/пуста.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== .env ==="
awk -F= '/^[A-Z]/ { print $1 "=" (length($2) > 0 ? "SET" : "EMPTY") }' .env

echo
echo "=== БД ==="
.venv/bin/python - <<'PY'
import sqlite3
con = sqlite3.connect("data/avito_dvijenia.db")
for label, sql in [
    ("товары по статусам", "select status, count(*) from product group by 1 order by 2 desc"),
    ("объявления по состояниям", "select state, count(*) from listing group by 1 order by 2 desc"),
    ("медиа по видам", "select kind, count(*) from mediaasset group by 1"),
]:
    print(label + ":")
    try:
        rows = list(con.execute(sql))
    except Exception as exc:  # таблицы может не быть
        print("   ", exc)
        continue
    if not rows:
        print("    пусто")
    for row in rows:
        print("   ", row)
PY
