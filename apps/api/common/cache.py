from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 30.0


class FailOpenRedisCache(RedisCache):
    # Rate-limit counters protect the API but aren't worth failing a request over, so a Redis error reads as a miss
    # and skips the write. Redis is then left alone for a while, so an outage doesn't add a timeout to every request.
    # Only get and set are wrapped because they are all DRF's throttle calls.

    def __init__(self, server: str, params: dict[str, Any]):
        super().__init__(server, params)
        self._unavailable_until = 0.0

    def _is_available(self) -> bool:
        return time.monotonic() >= self._unavailable_until

    def _record_failure(self, operation: str, error: RedisError) -> None:
        if self._is_available():
            log.warning(
                "cache: Redis %s failed (%s); running without it for %.0f seconds",
                operation,
                error,
                RETRY_AFTER_SECONDS,
            )
        self._unavailable_until = time.monotonic() + RETRY_AFTER_SECONDS

    def get(self, key: Any, default: Any | None = None, version: int | None = None) -> Any:
        if self._is_available():
            try:
                return super().get(key, default, version)
            except RedisError as error:
                self._record_failure("get", error)
        return default

    def set(self, key: Any, value: Any, timeout: Any = DEFAULT_TIMEOUT, version: int | None = None) -> None:
        if self._is_available():
            try:
                super().set(key, value, timeout, version)
            except RedisError as error:
                self._record_failure("set", error)
