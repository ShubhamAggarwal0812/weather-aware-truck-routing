from typing import Any

from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from common.ratelimit import add_to_window, limits, seconds_left


class SharedScopedRateThrottle(ScopedRateThrottle):
    cache = limits

    # DRF's own check reads the request history and writes it back, so concurrent requests from one client all
    # read the same history and pass.
    def allow_request(self, request: Request, view: Any) -> bool:
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.key = self.get_cache_key(request, view)
        # As in DRF, a scope whose rate is None isn't limited.
        if self.num_requests is None or self.duration is None or self.key is None:
            return True
        self.now = self.timer()
        return add_to_window(self.cache, self.key, 1, self.duration, self.now) <= self.num_requests

    def wait(self) -> float | None:
        return None if self.duration is None else seconds_left(self.duration, self.now)


def client_address(request: Request) -> str:
    # The address the throttles trust (NUM_PROXIES), so a client can't escape a limit by sending its own header.
    return BaseThrottle().get_ident(request)
