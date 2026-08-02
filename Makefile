.PHONY: help setup check test lint fix audit access sync sync-write categories admin-sync media-sync media-sync-write bot

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
	@echo "bot          - запустить Telegram-бота"

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

bot:
	bash scripts/run_bot.sh
