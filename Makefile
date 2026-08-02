.PHONY: help setup check test lint fix audit access sync sync-write categories admin-sync media-sync media-sync-write content-build feed-build budget-check planner-run bot web

help:
	@echo "setup        - создать venv и поставить зависимости"
	@echo "check        - линт + тесты (перед коммитом)"
	@echo "test         - только тесты"
	@echo "lint         - проверить стиль"
	@echo "fix          - автопочинить стиль"
	@echo "audit        - проверить, что секреты не утекли (перед push)"
	@echo "access       - проверить доступ к Avito API, обновить docs/api_notes.md"
	@echo "sync         - стянуть прайсы поставщика, показать диф (dry-run)"
	@echo "sync-write   - то же, но записать в БД"
	@echo "categories   - перегенерировать docs/categories.md"
	@echo "admin-sync   - синк таблицы-пульта: решения оператора + очередь модерации"
	@echo "media-sync   - скачать фото поставщика в MediaStore, показать диф (dry-run)"
	@echo "media-sync-write - то же, но реально скачать и записать MediaAsset"
	@echo "content-build - собрать Listing (5 гео-копий) для APPROVED-товаров"
	@echo "feed-build   - собрать и провалидировать XML фида (без обращения к Авито)"
	@echo "budget-check - живой read-only запрос баланса, проверка порога min_balance_rub"
	@echo "planner-run  - выбрать DRAFT-листинги под бюджет, запросить PUBLISH (dry-run)"
	@echo "bot          - запустить Telegram-бота"
	@echo "web          - запустить FastAPI (/feed.xml, /media/*, /health)"

setup:
	bash scripts/setup_venv.sh

check:
	bash scripts/check.sh

test:
	bash scripts/test.sh

lint:
	bash scripts/lint.sh

fix:
	bash scripts/lint.sh --fix

audit:
	bash scripts/audit_secrets.sh

access:
	bash scripts/run_cli.sh check-access

sync:
	bash scripts/run_cli.sh sources sync

sync-write:
	bash scripts/run_cli.sh sources sync --write

categories:
	bash scripts/run_cli.sh categories dump

admin-sync:
	bash scripts/run_cli.sh admin sync

media-sync:
	bash scripts/run_cli.sh media sync

media-sync-write:
	bash scripts/run_cli.sh media sync --write

content-build:
	bash scripts/run_cli.sh content build

feed-build:
	bash scripts/run_cli.sh feed build

budget-check:
	bash scripts/run_cli.sh budget check

planner-run:
	bash scripts/run_cli.sh planner run

bot:
	bash scripts/run_bot.sh

web:
	bash scripts/run_web.sh
