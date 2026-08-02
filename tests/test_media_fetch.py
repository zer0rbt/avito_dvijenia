from __future__ import annotations

import httpx
import pytest

import media.fetch as fetch_module
from media.fetch import fetch_photo_bytes, fetch_post_photo_urls, parse_post_url

# Обрезанный, но структурно настоящий фрагмент разметки t.me/s/<channel> —
# фото поста зашито в background-image инлайн-стиля <a>, не в <img src>.
CHANNEL_PREVIEW_HTML = """
<div class="tgme_widget_message" data-post="best_dropship/1545">
  <a class="tgme_widget_message_photo_wrap"
     style="background-image:url('https://cdn.tg/photo1.jpg')"></a>
</div>
<div class="tgme_widget_message" data-post="best_dropship/1545">
  <a class="tgme_widget_message_photo_wrap"
     style="background-image:url('https://cdn.tg/photo2.jpg')"></a>
</div>
<div class="tgme_widget_message" data-post="best_dropship/9999">
  <a class="tgme_widget_message_photo_wrap"
     style="background-image:url('https://cdn.tg/other.jpg')"></a>
</div>
"""


def test_parse_post_url_extracts_channel_and_message_id():
    assert parse_post_url("https://t.me/best_dropship/1545") == ("best_dropship", "1545")


def test_parse_post_url_returns_none_for_unrelated_string():
    assert parse_post_url("не ссылка на телеграм") is None


def test_fetch_post_photo_urls_matches_only_target_post(monkeypatch):
    monkeypatch.setattr(
        fetch_module, "_fetch_channel_preview", lambda channel, **_: CHANNEL_PREVIEW_HTML
    )
    urls = fetch_post_photo_urls("https://t.me/best_dropship/1545")
    assert urls == ["https://cdn.tg/photo1.jpg", "https://cdn.tg/photo2.jpg"]


def test_fetch_post_photo_urls_empty_when_post_out_of_preview_window(monkeypatch):
    monkeypatch.setattr(
        fetch_module, "_fetch_channel_preview", lambda channel, **_: CHANNEL_PREVIEW_HTML
    )
    urls = fetch_post_photo_urls("https://t.me/best_dropship/424242")
    assert urls == []


def test_fetch_post_photo_urls_returns_empty_for_non_tg_url():
    assert fetch_post_photo_urls("https://example.com/not-telegram") == []


def test_fetch_photo_bytes_returns_body(monkeypatch):
    class FakeResponse:
        content = b"jpeg-bytes"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    assert fetch_photo_bytes("https://cdn.tg/photo1.jpg") == b"jpeg-bytes"


def test_fetch_photo_bytes_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def failing_get(*_a, **_k):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", failing_get)
    monkeypatch.setattr(fetch_module.time, "sleep", lambda _: None)

    with pytest.raises(httpx.ConnectError):
        fetch_photo_bytes("https://cdn.tg/photo1.jpg", retries=3)
    assert calls["n"] == 3
