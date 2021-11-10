import time
import unittest.mock

import pytest

from zigpy.ota.cached_client import ExpiringCache


@pytest.fixture
def time_travel():
    original = time.time
    offset = 0

    def inner(seconds):
        nonlocal offset
        offset = seconds

    with unittest.mock.patch.object(time, "time", wraps=lambda: original() + offset):
        yield inner


def test_time_travel(time_travel):
    now = time.time()

    time_travel(-now)
    assert time.time() < 1

    time_travel(0)
    assert time.time() - now < 1

    time_travel(1)
    assert 1 < time.time() - now < 2

    time_travel(100)
    assert 100 < time.time() - now < 101


@pytest.fixture
def cache():
    return ExpiringCache()


def test_cache_empty(cache):
    assert len(cache.keys()) == 0

    with pytest.raises(KeyError):
        cache["does_not_exist"]

    assert len(cache.keys()) == 0
    assert "does_not_exist" not in cache


def test_cache_get_set(cache, time_travel):
    now = time.time()

    cache.set("expired", 123, expire_in=5)
    assert len(cache.keys()) == 1
    assert cache["expired"] == 123
    assert abs(cache.expires("expired") - (now + 5)) < 1

    time_travel(4)
    assert len(cache.keys()) == 1
    assert cache["expired"] == 123
    assert abs(cache.expires("expired") - (now + 5)) < 1

    time_travel(5)

    with pytest.raises(KeyError):
        cache["expired"]

    with pytest.raises(KeyError):
        cache.expires("expired")

    assert "expired" not in cache


def test_cache_negative_expiration(cache):
    cache.set("expired", 123, expire_in=0)
    assert "expired" not in cache

    cache.set("expired 2", 123, expire_in=-1)
    assert "expired 2" not in cache


def test_cache_delete_then_get(cache):
    cache.set("deleted", 123, expire_in=5)
    cache.delete("deleted")

    with pytest.raises(KeyError):
        cache["deleted"]

    assert "deleted" not in cache


def test_cache_delete_expired(cache, time_travel):
    cache.set("expired", 123, expire_in=5)
    time_travel(5)

    with pytest.raises(KeyError):
        cache.delete("expired")

    with pytest.raises(KeyError):
        cache["expired"]

    assert "deleted" not in cache


def test_cache_repr(cache, time_travel):
    assert "0 keys" in repr(cache)

    cache.set("key 1", 123, expire_in=1)
    assert "1 keys" in repr(cache)

    cache.set("key 2", 456, expire_in=5)
    assert "2 keys" in repr(cache)

    time_travel(2)
    assert "1 keys" in repr(cache)

    time_travel(6)
    assert "0 keys" in repr(cache)
