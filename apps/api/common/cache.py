from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 30.0

# Django gives every thread its own cache instance, so the back-off lives here, per server, where all of
# a process's threads see it. Otherwise each thread would wait out its own timeout during an outage.
_unavailable_until: dict[str, float] = {}


class FailOpenRedisCache(RedisCache):
    # Rate-limit counters protect the API but aren't worth failing a request over, so a Redis error reads as
    # an empty counter and skips the write. Redis is then left alone for a while, so an outage doesn't add a
    # timeout to every request. Only add and incr are wrapped because they are all common.ratelimit calls.

    def __init__(self, server: str, params: dict[str, Any]):
        super().__init__(server, params)
        self._server = server

    def _is_available(self) -> bool:
        return time.monotonic() >= _unavailable_until.get(self._server, 0.0)

    def _record_failure(self, operation: str, error: RedisError) -> None:
        if self._is_available():
            log.warning(
                "cache: Redis %s failed (%s); running without it for %.0f seconds",
                operation,
                error,
                RETRY_AFTER_SECONDS,
            )
        _unavailable_until[self._server] = time.monotonic() + RETRY_AFTER_SECONDS

    def add(self, key: Any, value: Any, timeout: Any = DEFAULT_TIMEOUT, version: int | None = None) -> bool:
        if self._is_available():
            try:
                return super().add(key, value, timeout, version)
            except RedisError as error:
                self._record_failure("add", error)
        return False

    def incr(self, key: Any, delta: int = 1, version: int | None = None) -> int:
        if self._is_available():
            try:
                return super().incr(key, delta, version)
            except RedisError as error:
                self._record_failure("incr", error)
        return 0
