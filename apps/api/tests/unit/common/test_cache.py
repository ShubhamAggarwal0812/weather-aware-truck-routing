import pytest
from django.core.cache import cache as default_cache
from django.core.cache import caches
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from common import cache as cache_module
from common.api.throttling import SharedScopedRateThrottle
from common.cache import RETRY_AFTER_SECONDS, FailOpenRedisCache
from config.settings.base import env_int, redis_url


def unreachable_cache():
    return FailOpenRedisCache(
        "redis://127.0.0.1:1/0", {"OPTIONS": {"socket_connect_timeout": 0.5, "socket_timeout": 0.5}}
    )


def plan_request():
    view = type("View", (), {"throttle_scope": "plan"})()
    return Request(APIRequestFactory().post("/", REMOTE_ADDR="203.0.113.9")), view


def test_should_return_the_default_when_redis_is_unreachable():
    assert unreachable_cache().get("key", "fallback") == "fallback"


def test_should_skip_the_write_when_redis_is_unreachable():
    assert unreachable_cache().set("key", 1, 60) is None


def test_should_leave_redis_alone_for_a_while_after_a_failure(monkeypatch):
    attempts = []

    def failing_get(self, key, default=None, version=None):
        attempts.append(key)
        raise RedisConnectionError("refused")

    monkeypatch.setattr(RedisCache, "get", failing_get)
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])
    cache = unreachable_cache()
    assert cache.get("first", 0) == 0
    assert cache.get("second", 0) == 0
    assert attempts == ["first"]
    now[0] += RETRY_AFTER_SECONDS
    cache.get("third", 0)
    assert attempts == ["first", "third"]


def test_should_let_requests_through_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(SharedScopedRateThrottle, "cache", unreachable_cache())
    monkeypatch.setattr(SharedScopedRateThrottle, "THROTTLE_RATES", {"plan": "1/min"})
    request, view = plan_request()
    assert all(SharedScopedRateThrottle().allow_request(request, view) for _ in range(3))


def test_should_count_rate_limits_in_the_limits_cache_not_the_response_cache(monkeypatch):
    monkeypatch.setattr(SharedScopedRateThrottle, "THROTTLE_RATES", {"plan": "1/min"})
    caches["limits"].clear()
    request, view = plan_request()
    throttle = SharedScopedRateThrottle()
    assert throttle.allow_request(request, view)
    assert not SharedScopedRateThrottle().allow_request(request, view)
    key = throttle.get_cache_key(request, view)
    assert caches["limits"].get(key)
    assert default_cache.get(key) is None


def test_should_use_no_redis_when_neither_variable_is_set(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("KV_URL", raising=False)
    assert redis_url() == ""


def test_should_fall_back_to_kv_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("KV_URL", "rediss://default:secret@example.redis.test:6379")
    assert redis_url() == "rediss://default:secret@example.redis.test:6379"


def test_should_prefer_redis_url_over_kv_url(monkeypatch):
    monkeypatch.setenv("KV_URL", "rediss://default:secret@example.redis.test:6379")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    assert redis_url() == "redis://redis:6379/0"


def test_should_ignore_a_rest_url_with_a_warning(monkeypatch):
    monkeypatch.delenv("KV_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "https://example.redis.test")
    with pytest.warns(UserWarning, match="REDIS_URL"):
        assert redis_url() == ""


@pytest.mark.parametrize(("value", "expected"), [("", 1), ("  ", 1), ("2", 2)])
def test_should_read_an_integer_setting_and_use_the_default_when_it_is_blank(monkeypatch, value, expected):
    monkeypatch.setenv("NUM_PROXIES", value)
    assert env_int("NUM_PROXIES", 1) == expected
