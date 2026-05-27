from __future__ import annotations

import json

from app.graphrag.utils.cache import MemoryCache


def test_memory_cache_prunes_expired_entries_on_set(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr("app.graphrag.utils.cache.time.time", lambda: now)
    cache = MemoryCache()
    assert cache.setex("old", 10, json.dumps({"value": "old"}))

    now = 1011.0
    assert cache.setex("new", 10, json.dumps({"value": "new"}))

    assert "old" not in cache._cache
    assert cache.get("new") == json.dumps({"value": "new"})


def test_memory_cache_prunes_overflow_by_nearest_expiry(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr("app.graphrag.utils.cache.time.time", lambda: now)
    cache = MemoryCache(max_entries=2)
    assert cache.setex("first", 10, json.dumps("first"))
    assert cache.setex("second", 20, json.dumps("second"))
    assert cache.setex("third", 30, json.dumps("third"))

    assert "first" not in cache._cache
    assert "second" in cache._cache
    assert "third" in cache._cache
