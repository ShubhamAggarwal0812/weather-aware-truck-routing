"""Hourly forecasts from Open-Meteo, batched, cached, and sampled at exact times.

Open-Meteo takes many coordinates per request, so a whole route's checkpoints
(or a whole corridor grid) costs a handful of HTTP calls. Units are requested
directly in mph and inches.

Timing. Wind and temperature are instantaneous values at each hour, so they are
interpolated linearly to the ETA. Rain, showers and snowfall are totals for the
hour *ending* at each timestamp, so a truck passing at 14:37 gets the 15:00
value (the 14:00-15:00 total). That total is also the in/hr rate the risk table
uses.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.core.cache import cache

from trips.domain.geo import LatLon
from trips.domain.risk import Conditions
from trips.services.http import UpstreamError, request_json

log = logging.getLogger(__name__)

HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m")
BATCH_SIZE = 100
MAX_PARALLEL = 4
CACHE_TTL_S = 30 * 60
FORECAST_DAYS = 16
HOUR = timedelta(hours=1)


class WeatherError(Exception):
    """Weather could not be fetched. The message is safe to show to the user."""


def floor_hour(t: datetime) -> datetime:
    return t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class Sample:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    temp_f: float

    @property
    def conditions(self) -> Conditions:
        return Conditions(self.wind_mph, self.rain_in_hr, self.snow_in_hr)


@dataclass(frozen=True)
class HourlySeries:
    """One location's forecast, one value per hour starting at ``start`` (UTC)."""

    start: datetime
    wind_mph: tuple[float, ...]
    gust_mph: tuple[float, ...]
    rain_in: tuple[float, ...]  # rain + showers in the hour ending at each timestamp
    snow_in: tuple[float, ...]
    temp_f: tuple[float, ...]

    def __len__(self) -> int:
        return len(self.wind_mph)

    def hour_index(self, t: datetime) -> int:
        return int((floor_hour(t) - self.start) / HOUR)

    def covers(self, t: datetime) -> bool:
        i = self.hour_index(t)
        return i >= 0 and i + 1 < len(self)

    def at(self, t: datetime) -> Sample:
        offset_h = (t - self.start) / HOUR
        i = min(max(0, math.floor(offset_h)), len(self) - 1)
        frac = min(max(0.0, offset_h - i), 1.0)
        nxt = min(i + 1, len(self) - 1)

        def lerp(values: tuple[float, ...]) -> float:
            return values[i] + (values[nxt] - values[i]) * frac

        return Sample(
            wind_mph=lerp(self.wind_mph),
            gust_mph=lerp(self.gust_mph),
            rain_in_hr=self.rain_in[nxt],
            snow_in_hr=self.snow_in[nxt],
            temp_f=lerp(self.temp_f),
        )

    def hour(self, i: int) -> Sample:
        """Conditions for the hour starting at ``start + i`` hours."""
        nxt = min(i + 1, len(self) - 1)
        return Sample(self.wind_mph[i], self.gust_mph[i], self.rain_in[nxt], self.snow_in[nxt], self.temp_f[i])


def forecast_limit() -> datetime:
    """Latest hour Open-Meteo forecasts for (16 days from today, UTC)."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=FORECAST_DAYS) - HOUR


class OpenMeteoClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.OPEN_METEO_BASE_URL).rstrip("/")
        self.api_key = settings.OPEN_METEO_API_KEY if api_key is None else api_key

    def hourly(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        """Forecasts for ``points`` from ``start`` to ``end`` (both whole UTC hours, inclusive)."""
        start, end = floor_hour(start), floor_hour(end)
        keys = [_cache_key(p, start, end) for p in points]
        cached = cache.get_many(keys)
        missing = [i for i, k in enumerate(keys) if k not in cached]
        if missing:
            batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
                results = list(pool.map(lambda b: self._fetch([points[i] for i in b], start, end), batches))
            fresh = {keys[i]: series for batch, out in zip(batches, results) for i, series in zip(batch, out)}
            cache.set_many(fresh, CACHE_TTL_S)
            cached.update(fresh)
        log.info("weather: %d points, %d fetched", len(points), len(missing))
        return [cached[k] for k in keys]

    def _fetch(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        form = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "timezone": "GMT",
            "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        }
        if self.api_key:
            form["apikey"] = self.api_key
        try:
            data = request_json("POST", f"{self.base_url}/v1/forecast", service="open-meteo", data=form)
        except UpstreamError as exc:
            if exc.status == 429:
                raise WeatherError("The weather service's rate limit was reached. Try again in a minute.") from exc
            raise WeatherError("The weather service is unavailable. Try again in a minute.") from exc
        locations = data if isinstance(data, list) else [data]
        if len(locations) != len(points):
            raise WeatherError("The weather service returned an incomplete forecast.")
        expected_first = start.strftime("%Y-%m-%dT%H:%M")
        if any(loc["hourly"]["time"][0] != expected_first for loc in locations):
            raise WeatherError("The weather service returned an unexpected time window.")
        return [_parse(loc["hourly"], start) for loc in locations]


def _cache_key(p: LatLon, start: datetime, end: datetime) -> str:
    return f"om:{p[0]:.4f},{p[1]:.4f}:{start:%Y%m%d%H}:{end:%Y%m%d%H}"


def _filled(values: list[float | None], default: float = 0.0) -> tuple[float, ...]:
    """Replace gaps with the previous value (models occasionally drop an hour)."""
    out: list[float] = []
    last = next((v for v in values if v is not None), default)
    for v in values:
        last = v if v is not None else last
        out.append(float(last))
    return tuple(out)


def _parse(hourly: dict, start: datetime) -> HourlySeries:
    rain = _filled(hourly["rain"])
    showers = _filled(hourly["showers"])
    return HourlySeries(
        start=start,
        wind_mph=_filled(hourly["wind_speed_10m"]),
        gust_mph=_filled(hourly["wind_gusts_10m"]),
        rain_in=tuple(r + s for r, s in zip(rain, showers)),
        snow_in=_filled(hourly["snowfall"]),
        temp_f=_filled(hourly["temperature_2m"]),
    )
