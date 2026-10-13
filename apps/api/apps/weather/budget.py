# Open-Meteo counts each location as a call, and the free tier allows about 10,000 a day per server IP. The
# request throttles count requests, not locations, and one plan or heatmap can need hundreds, so a client asking
# for a new departure hour or new lines each time could spend the whole day's quota in a few minutes.

from __future__ import annotations

import time
from datetime import UTC, datetime

from django.conf import settings

from common.ratelimit import add_to_window, limits, parse_rate, seconds_left

from .exceptions import WeatherError


class WeatherBudget:
    def __init__(self, client: str, rate: str | None = None):
        self.key = f"weather_budget_{client}"
        self.rate = parse_rate(settings.WEATHER_BUDGET if rate is None else rate)

    def spend(self, locations: int) -> None:
        if self.rate is None or locations == 0:
            return
        allowed_locations, window_seconds = self.rate
        if locations > allowed_locations:
            raise WeatherError("This trip needs more weather data than one connection may fetch.", status=422)
        now = time.time()
        if add_to_window(limits, self.key, locations, window_seconds, now) > allowed_locations:
            # Nothing is fetched, so nothing is spent, and a smaller request can still fit.
            add_to_window(limits, self.key, -locations, window_seconds, now)
            resets = datetime.fromtimestamp(now + seconds_left(window_seconds, now), UTC)
            raise WeatherError(
                "This connection has fetched as much weather data as it may for now. "
                f"The allowance resets at {resets:%H:%M} UTC.",
                status=429,
            )
