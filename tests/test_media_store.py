from __future__ import annotations

import pytest

from media.store import LocalFSStore, content_key


def test_local_fs_store_save_load_roundtrip(tmp_path):
    store = LocalFSStore(tmp_path)
    url = store.save("raw/item_1/photo.jpg", b"binary-data")

    assert store.exists("raw/item_1/photo.jpg")
    assert store.load("raw/item_1/photo.jpg") == b"binary-data"
    assert url.startswith("file://")


def test_local_fs_store_public_url_uses_configured_base(tmp_path):
    store = LocalFSStore(tmp_path, public_base_url="https://cdn.example.com/media")
    url = store.save("raw/item_1/photo.jpg", b"data")
    assert url == "https://cdn.example.com/media/raw/item_1/photo.jpg"


def test_local_fs_store_rejects_path_traversal(tmp_path):
    store = LocalFSStore(tmp_path)
    with pytest.raises(ValueError):
        store.save("../outside.jpg", b"data")


def test_content_key_is_stable_and_content_addressed():
    key_a = content_key(b"same-bytes", prefix="raw/item_1")
    key_b = content_key(b"same-bytes", prefix="raw/item_1")
    key_c = content_key(b"different-bytes", prefix="raw/item_1")

    assert key_a == key_b
    assert key_a != key_c
    assert key_a.startswith("raw/item_1/")
    assert key_a.endswith(".jpg")
