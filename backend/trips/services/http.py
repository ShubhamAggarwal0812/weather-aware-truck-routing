"""One shared HTTP client for all providers, with a single retry on transient failures."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

_client = httpx.Client(
    timeout=httpx.Timeout(20.0, connect=5.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    transport=httpx.HTTPTransport(retries=1),
    headers={"User-Agent": "weather-aware-truck-routing/1.0"},
)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class UpstreamError(Exception):
    def __init__(self, service: str, detail: str, status: int | None = None, body: str = ""):
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.status = status
        self.body = body


def request_json(method: str, url: str, *, service: str, **kwargs: Any) -> Any:
    """Send a request and decode JSON. Retries once on 429/5xx and on network errors."""
    for attempt in (1, 2):
        started = time.monotonic()
        try:
            response = _client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise UpstreamError(service, f"network error: {exc.__class__.__name__}") from exc
            time.sleep(0.4)
            continue
        elapsed_ms = (time.monotonic() - started) * 1000
        log.info("%s %s -> %s in %.0f ms", service, method, response.status_code, elapsed_ms)
        if response.status_code in RETRY_STATUSES and attempt == 1:
            time.sleep(0.6)
            continue
        if response.status_code >= 400:
            raise UpstreamError(service, f"HTTP {response.status_code}", response.status_code, response.text[:500])
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(service, "invalid JSON") from exc
    raise AssertionError("unreachable")
