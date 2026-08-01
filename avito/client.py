"""HTTP-клиент Avito API.

ВАЖНО про источники достоверности эндпоинтов. Портал developers.avito.ru —
JS-SPA без публично читаемой спецификации, поэтому пути ниже собраны из
независимых генерируемых клиентов (covox/avito_api, avito-php-api-items,
n8n-nodes-avito-api), которые обычно строятся из офиц. OpenAPI-описания,
и перепроверены между собой. Каждый метод помечен:

  CONFIRMED  — путь совпал минимум в 2 независимых источниках
  CANDIDATE  — встречен в одном источнике или из имени инструмента
               стороннего MCP-сервера, путь не подтверждён напрямую
  UNKNOWN    — официального пути найти не удалось, endpoint не реализован

Ключевая находка по Автозагрузке (важно для архитектуры): нет подтверждённого
публичного эндпоинта "запустить выгрузку". Реальный механизм — Avito сам
периодически опрашивает наш публичный URL фида по расписанию, заданному
в ЛК (рекомендуется «автоматически, при каждом обращении» при <10000
объявлений — наш случай). Мы не дёргаем upload, мы просто держим
/feed.xml в актуальном состоянии, а результат каждого цикла читаем через
CONFIRMED reports-эндпоинты.

check-access (cli.py) прогоняет все методы этого файла по-настоящему и
пишет результат в docs/api_notes.md — так расхождения между источниками
и реальностью аккаунта фиксируются один раз, а не перепроверяются каждый
запуск вслепую.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from avito.auth import fetch_access_token
from core.config import get_settings

BASE_URL = "https://api.avito.ru"


class AvitoApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:300]}")


@dataclass
class ProbeResult:
    name: str
    confidence: str  # CONFIRMED | CANDIDATE
    method: str
    path: str
    ok: bool
    status: int | None
    note: str


class AvitoClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self._settings = get_settings()
        self._http = httpx.Client(base_url=BASE_URL, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AvitoClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- транспорт -----------------------------------------------------

    def _headers(self) -> dict[str, str]:
        token = fetch_access_token()
        return {"Authorization": f"Bearer {token}"}

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._http.request(method, path, headers=self._headers(), **kwargs)
        if resp.status_code >= 400:
            raise AvitoApiError(method, path, resp.status_code, resp.text)
        return resp

    # -- user / account. CONFIRMED (совпадает в covox/avito_api и n8n-nodes-avito-api)

    def get_self(self) -> dict:
        """GET /core/v1/accounts/self — профиль текущего аккаунта, содержит user_id."""
        return self.request("GET", "/core/v1/accounts/self").json()

    def get_balance(self, user_id: str) -> dict:
        """GET /core/v1/accounts/{user_id}/balance/ — баланс кошелька/аванса."""
        return self.request("GET", f"/core/v1/accounts/{user_id}/balance/").json()

    def get_operations_history(self, user_id: str, **params: Any) -> dict:
        """POST /core/v1/accounts/operations_history/ — история операций по счёту."""
        return self.request(
            "POST", "/core/v1/accounts/operations_history/", json=params
        ).json()

    # -- items. CONFIRMED (covox/avito_api README + AutoloadApi.md пересекаются)

    def get_item(self, user_id: str, item_id: str) -> dict:
        """GET /core/v1/accounts/{user_id}/items/{item_id}/"""
        return self.request(
            "GET", f"/core/v1/accounts/{user_id}/items/{item_id}/"
        ).json()

    def get_item_stats(self, user_id: str, **payload: Any) -> dict:
        """POST /core/v1/accounts/{user_id}/stats/items"""
        return self.request(
            "POST", f"/core/v1/accounts/{user_id}/stats/items", json=payload
        ).json()

    def get_account_spendings(self, user_id: str, **payload: Any) -> dict:
        """CANDIDATE: POST /stats/v2/accounts/{user_id}/spendings (n8n-nodes-avito-api)."""
        return self.request(
            "POST", f"/stats/v2/accounts/{user_id}/spendings", json=payload
        ).json()

    # -- autoload. CONFIRMED только READ-эндпоинты (совпали в covox/avito_api и avito_api2)

    def get_autoload_item(self, user_id: str, ad_id: str) -> dict:
        """GET /autoload/v1/accounts/{user_id}/items/{ad_id}/ — статус выгрузки объявления."""
        return self.request(
            "GET", f"/autoload/v1/accounts/{user_id}/items/{ad_id}/"
        ).json()

    def get_autoload_last_report(self, user_id: str) -> dict:
        """GET /autoload/v1/accounts/{user_id}/reports/last_report/"""
        return self.request(
            "GET", f"/autoload/v1/accounts/{user_id}/reports/last_report/"
        ).json()

    def get_autoload_report(self, user_id: str, report_id: str) -> dict:
        """GET /autoload/v1/accounts/{user_id}/reports/{report_id}/"""
        return self.request(
            "GET", f"/autoload/v1/accounts/{user_id}/reports/{report_id}/"
        ).json()

    def get_autoload_reports(self, user_id: str, **params: Any) -> dict:
        """GET /autoload/v1/accounts/{user_id}/reports/"""
        return self.request(
            "GET", f"/autoload/v1/accounts/{user_id}/reports/", params=params
        ).json()

    # -- messenger. CONFIRMED (n8n-nodes-avito-api)

    def get_chats(self, user_id: str, **params: Any) -> dict:
        return self.request(
            "GET", f"/messenger/v2/accounts/{user_id}/chats", params=params
        ).json()

    def get_messages(self, user_id: str, chat_id: str, **params: Any) -> dict:
        return self.request(
            "GET",
            f"/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
            params=params,
        ).json()

    def send_message(self, user_id: str, chat_id: str, text: str) -> dict:
        return self.request(
            "POST",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
            json={"message": {"text": text}, "type": "text"},
        ).json()

    # -- диагностика (Э0) -----------------------------------------------

    def probe_all(self, user_id: str | None = None) -> list[ProbeResult]:
        """Прогоняет ключевые read-only методы и репортит, что реально работает
        на этом аккаунте. Не гадаем в коде системы — фиксируем факт здесь.
        """
        results: list[ProbeResult] = []

        def _probe(name: str, confidence: str, method: str, path: str, fn) -> str | None:
            try:
                fn()
                results.append(ProbeResult(name, confidence, method, path, True, 200, "ok"))
                return None
            except AvitoApiError as e:
                results.append(
                    ProbeResult(name, confidence, method, path, False, e.status, e.body[:200])
                )
                return None
            except Exception as e:  # noqa: BLE001 — диагностика, глотаем всё осознанно
                results.append(
                    ProbeResult(name, confidence, method, path, False, None, str(e)[:200])
                )
                return None

        _probe(
            "get_self", "CONFIRMED", "GET", "/core/v1/accounts/self", self.get_self
        )

        if user_id:
            _probe(
                "get_balance",
                "CONFIRMED",
                "GET",
                f"/core/v1/accounts/{user_id}/balance/",
                lambda: self.get_balance(user_id),
            )
            _probe(
                "get_autoload_last_report",
                "CONFIRMED",
                "GET",
                f"/autoload/v1/accounts/{user_id}/reports/last_report/",
                lambda: self.get_autoload_last_report(user_id),
            )
            _probe(
                "get_autoload_reports",
                "CONFIRMED",
                "GET",
                f"/autoload/v1/accounts/{user_id}/reports/",
                lambda: self.get_autoload_reports(user_id, per_page=1, page=1),
            )
            _probe(
                "get_chats",
                "CONFIRMED",
                "GET",
                f"/messenger/v2/accounts/{user_id}/chats",
                lambda: self.get_chats(user_id, limit=1),
            )

        return results
