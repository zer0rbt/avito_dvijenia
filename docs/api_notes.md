# Avito API — фактическая проверка доступа

<!-- Файл ПЕРЕЗАПИСЫВАЕТСЯ целиком командой `make access`.
     Не дописывай сюда выводы руками — они будут стёрты при следующем
     прогоне. Разбор и решения по находкам живут в docs/BACKLOG.md. -->

Прогнано: 2026-08-02T01:23:46+00:00
user_id: `198989053`

Пути собраны из независимых сторонних источников (не из офиц.
спецификации — портал developers.avito.ru отдаёт JS-SPA без
публично читаемого текста). См. avito/client.py про CONFIRMED/CANDIDATE.

| Метод | Уверенность | HTTP | Путь | Статус | Заметка |
|---|---|---|---|---|---|
| get_self | CONFIRMED | GET | `/core/v1/accounts/self` | OK | ok |
| get_balance | CONFIRMED | GET | `/core/v1/accounts/198989053/balance/` | OK | ok |
| get_autoload_last_report | CONFIRMED | GET | `/autoload/v1/accounts/198989053/reports/last_report/` | FAIL 404 | {"message":"This route is temporarily unavailable"} |
| get_autoload_reports | CONFIRMED | GET | `/autoload/v1/accounts/198989053/reports/` | FAIL 404 | {"message":"This route is temporarily unavailable"} |
| get_chats | CONFIRMED | GET | `/messenger/v2/accounts/198989053/chats` | OK | ok |
| get_operations_history | CANDIDATE | POST | `/core/v1/accounts/operations_history/` | OK | ok |

## Что с этим делать

Разбор результатов — в [BACKLOG.md](BACKLOG.md):

- `B-003` — баланс отдаёт 0 ₽ при озвученных ~900 ₽;
- `B-004` — autoload-эндпоинты дают 404, перепроверить после
  подключения Автозагрузки в ЛК.
