#!/usr/bin/env bash
# Публичный адрес для /feed.xml и /media/* через Cloudflare Tunnel (B-025).
#
# Зачем: эндпоинта «запусти выгрузку» у Авито нет — Автозагрузка сама
# опрашивает наш URL по расписанию из ЛК. Без адреса, доступного снаружи,
# не работает ни публикация, ни затирка.
#
# Скрипт НИЧЕГО не публикует сам: он поднимает туннель и печатает адрес.
# Вписать адрес в .env и в ЛК — ручной шаг, намеренно.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"

if ! command -v cloudflared >/dev/null 2>&1; then
    cat <<'EOF'
cloudflared не установлен. Поставить (Debian/Ubuntu):

  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
https://pkg.cloudflare.com/cloudflared any main" \
    | sudo tee /etc/apt/sources.list.d/cloudflared.list
  sudo apt update && sudo apt install cloudflared

EOF
    exit 1
fi

if ! curl -fsS --max-time 3 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo "На localhost:${PORT} никто не отвечает. Сначала подними сервер: make web"
    exit 1
fi

cat <<EOF
Поднимаю туннель на localhost:${PORT}.

Дальше руками, скрипт этого не делает:
  1. взять из вывода ниже адрес https://<...>.trycloudflare.com;
  2. вписать его в .env в PUBLIC_BASE_URL и MEDIA_STORE_PUBLIC_BASE_URL;
  3. этот же адрес + /feed.xml — в ЛК → Автозагрузка → настройки профиля;
  4. проверить снаружи: curl https://<...>.trycloudflare.com/health

ВНИМАНИЕ: пробный туннель выдаёт НОВЫЙ адрес при каждом запуске, а адрес
прописан в ЛК. Для боевой работы нужен именованный туннель или домен на
VPS (Э10), иначе после каждого перезапуска Авито будет ходить в никуда.

EOF

exec cloudflared tunnel --url "http://localhost:${PORT}"
