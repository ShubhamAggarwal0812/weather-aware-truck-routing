from typing import cast

from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.utils.connection import ConnectionProxy
from rest_framework.throttling import ScopedRateThrottle


class SharedScopedRateThrottle(ScopedRateThrottle):
    # A proxy, like django.core.cache.cache, because one cache instance must not be shared across threads.
    cache = cast(BaseCache, ConnectionProxy(caches, "limits"))
