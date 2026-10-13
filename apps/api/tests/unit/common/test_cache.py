import threading
from concurrent.futures import ThreadPoolExecutor

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
from common.ratelimit import window_key
from config.settings.base import env_int, redis_url


def unreachable_cache():
    return FailOpenRedisCache(
        "redis://127.0.0.1:1/0", {"OPTIONS": {"socket_connect_timeout": 0.5, "socket_timeout": 0.5}}
    )


def plan_request():
    view = type("View", (), {"throttle_scope": "plan"})()
    return Request(APIRequestFactory().post("/", REMOTE_ADDR="203.0.113.9")), view


@pytest.fixture(autouse=True)
def redis_available():
    cache_module._unavailable_until.clear()
    yield
    cache_module._unavailable_until.clear()


def failing_increment(attempts):
    def increment(self, key, delta=1, version=None):
        attempts.append(key)
        raise RedisConnectionError("refused")

    return increment


def test_should_read_an_empty_counter_when_redis_is_unreachable():
    assert unreachable_cache().incr("key", 5) == 0


def test_should_skip_the_write_when_redis_is_unreachable():
    assert unreachable_cache().add("key", 0, 60) is False


def test_should_leave_redis_alone_for_a_while_after_a_failure(monkeypatch):
    attempts = []
    monkeypatch.setattr(RedisCache, "incr", failing_increment(attempts))
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])
    cache = unreachable_cache()
    assert cache.incr("first") == 0
    assert cache.incr("second") == 0
    assert attempts == ["first"]
    now[0] += RETRY_AFTER_SECONDS
    cache.incr("third")
    assert attempts == ["first", "third"]


def test_should_back_off_in_every_thread_after_one_thread_sees_a_failure(monkeypatch):
    attempts = []
    monkeypatch.setattr(RedisCache, "incr", failing_increment(attempts))
    first_thread, second_thread = unreachable_cache(), unreachable_cache()
    first_thread.incr("first")
    assert second_thread.incr("second") == 0
    assert attempts == ["first"]


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
    counter = window_key(throttle.get_cache_key(request, view), throttle.duration, throttle.now)
    assert caches["limits"].get(counter) == 2
    assert default_cache.get(counter) is None


def test_should_let_only_the_rate_through_when_requests_arrive_at_once(monkeypatch):
    monkeypatch.setattr(SharedScopedRateThrottle, "THROTTLE_RATES", {"plan": "10/min"})
    caches["limits"].clear()
    request, view = plan_request()
    start = threading.Barrier(40)

    def attempt(_):
        start.wait()
        return SharedScopedRateThrottle().allow_request(request, view)

    with ThreadPoolExecutor(max_workers=40) as pool:
        allowed = list(pool.map(attempt, range(40)))
    assert allowed.count(True) == 10


def test_should_start_a_new_count_in_the_next_window_and_say_when_it_starts(monkeypatch):
    monkeypatch.setattr(SharedScopedRateThrottle, "THROTTLE_RATES", {"plan": "1/min"})
    caches["limits"].clear()
    request, view = plan_request()
    forty_five_seconds_into_a_minute = 100 * 60 + 45.0
    now = [forty_five_seconds_into_a_minute]
    monkeypatch.setattr(SharedScopedRateThrottle, "timer", lambda self: now[0])
    assert SharedScopedRateThrottle().allow_request(request, view)
    refused = SharedScopedRateThrottle()
    assert not refused.allow_request(request, view)
    assert refused.wait() == 15
    now[0] += 15
    assert SharedScopedRateThrottle().allow_request(request, view)


def test_should_not_limit_a_scope_whose_rate_is_none(monkeypatch):
    monkeypatch.setattr(SharedScopedRateThrottle, "THROTTLE_RATES", {"plan": None})
    caches["limits"].clear()
    request, view = plan_request()
    assert all(SharedScopedRateThrottle().allow_request(request, view) for _ in range(3))


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
