from __future__ import annotations

from content.dedup import is_too_similar, jaccard_similarity, shingles


def test_shingles_identical_text_gives_similarity_one():
    text = "быстрая коричневая лиса перепрыгнула через ленивую собаку у реки"
    assert jaccard_similarity(shingles(text), shingles(text)) == 1.0


def test_shingles_completely_different_text_gives_low_similarity():
    a = shingles("быстрая коричневая лиса перепрыгнула через ленивую собаку у реки")
    b = shingles("вчера был дождливый день и мы остались дома смотреть кино")
    assert jaccard_similarity(a, b) < 0.2


def test_is_too_similar_detects_near_duplicate():
    original = "Продаём кроссовки Nike размер 42 43 44 цвет черный доставка по России"
    near_duplicate = "Продаём кроссовки Nike размер 42 43 44 цвет черный доставка по стране"
    assert is_too_similar(near_duplicate, [original])


def test_is_too_similar_false_for_distinct_text():
    original = "Продаём кроссовки Nike размер 42 43 44 цвет черный доставка по России"
    distinct = "Худи Champion серого цвета размеры S M L отправка курьером"
    assert not is_too_similar(distinct, [original])


def test_is_too_similar_false_when_no_previous_versions():
    assert not is_too_similar("любой текст", [])
