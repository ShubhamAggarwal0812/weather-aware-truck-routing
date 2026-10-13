# Each window has its own key, so counting is one atomic increment: concurrent requests can't all read the same
# count and pass, as they can with a read followed by a write. A key is never read after its window ends, so its
# expiry only frees memory. A fixed window lets a client spend up to twice the rate across a window boundary,
# which is the price of that single step.

from __future__ import annotations

from typing import cast

from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.utils.connection import ConnectionProxy

SECONDS_PER_PERIOD = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# A proxy, like django.core.cache.cache, because one cache instance must not be shared across threads.
limits = cast(BaseCache, ConnectionProxy(caches, "limits"))


def window_key(key: str, window_seconds: int, now: float) -> str:
    return f"{key}:{int(now // window_seconds)}"


def seconds_left(window_seconds: int, now: float) -> float:
    return window_seconds - now % window_seconds


def add_to_window(cache: BaseCache, key: str, amount: int, window_seconds: int, now: float) -> int:
    counter = window_key(key, window_seconds, now)
    # Created inside its window, so it outlives the window.
    cache.add(counter, 0, window_seconds)
    try:
        return cache.incr(counter, amount)
    except ValueError:
        # Evicted between the two calls; the count starts again from this request.
        return amount


def parse_rate(rate: str) -> tuple[int, int] | None:
    if not rate.strip():
        return None
    count, _, period = rate.strip().partition("/")
    window_seconds = SECONDS_PER_PERIOD.get(period.strip()[:1])
    if not count.strip().isdigit() or window_seconds is None:
        raise ValueError(f"{rate!r} isn't a rate like 3000/day.")
    return int(count), window_seconds
