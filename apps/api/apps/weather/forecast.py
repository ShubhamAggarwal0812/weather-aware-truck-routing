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
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from django.conf import settings
from django.core.cache import cache

from common.geo import LatLon
from common.http import UpstreamError, request_json

from .exceptions import WeatherError

log = logging.getLogger(__name__)

HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m")
# Open-Meteo counts each location as one call (600/min, 10k/day on the free tier).
BATCH_SIZE = 50
MAX_PARALLEL = 6
# The free API's latency is usually ~0.3 s but has a long tail (5-30 s). A batch that
# hasn't answered by then is sent again and the first answer wins.
HEDGE_AFTER_S = 2.5
REQUEST_TIMEOUT_S = 15.0
_attempts = ThreadPoolExecutor(max_workers=2 * MAX_PARALLEL, thread_name_prefix="open-meteo")
CACHE_TTL_S = 30 * 60
FORECAST_DAYS = 16
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
TIME_FORMAT = "%Y-%m-%dT%H:%M"
INCOMPLETE_FORECAST = "The weather service returned an incomplete forecast."
# Models occasionally drop an hour; a longer run of nulls means the forecast stops short.
MAX_FILLED_GAP_HOURS = 3


def floor_hour(t: datetime) -> datetime:
    return t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class Sample:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    temp_f: float


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

    @property
    def last_hour(self) -> datetime:
        return self.start + (len(self) - 1) * HOUR

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


class ForecastSource(Protocol):
    """Anything that returns hourly series for points: the Open-Meteo client, or a fake in tests."""

    def hourly(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]: ...


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
        keys = [_cache_key(point, start) for point in points]
        cached = {key: series for key, series in cache.get_many(keys).items() if series.last_hour >= end}
        missing = [i for i, k in enumerate(keys) if k not in cached]
        if missing:
            # Whole days from the start, so trips that only differ in arrival time share the cached series.
            whole_days_end = start + math.ceil((end - start) / DAY) * DAY
            fetch_end = max(end, min(whole_days_end, forecast_limit()))
            batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
                results = list(
                    pool.map(
                        lambda batch: self._hedged([points[index] for index in batch], start, fetch_end),
                        batches,
                    )
                )
            fresh = {keys[i]: series for batch, out in zip(batches, results) for i, series in zip(batch, out)}
            cache.set_many(fresh, CACHE_TTL_S)
            cached.update(fresh)
        log.info("weather: %d points, %d fetched", len(points), len(missing))
        return [cached[k] for k in keys]

    def _hedged(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        """Fetch a batch; if it's slow, race a second identical request against it."""
        running = threading.Event()

        def first_attempt() -> list[HourlySeries]:
            running.set()
            return self._fetch(points, start, end)

        first = _attempts.submit(first_attempt)
        # Waiting for a free worker isn't slowness, and a hedge sent then would only queue behind it.
        running.wait()
        done, _ = wait([first], timeout=HEDGE_AFTER_S)
        if done:
            return first.result()
        log.info("weather: batch of %d slow after %.1f s, hedging", len(points), HEDGE_AFTER_S)

        def hedge() -> list[HourlySeries]:
            # The worker that finishes the first attempt can pick this up before it's cancelled.
            if first.done() and first.exception() is None:
                return first.result()
            return self._fetch(points, start, end)

        pending: set[Future[list[HourlySeries]]] = {first, _attempts.submit(hedge)}
        error: WeatherError | None = None
        try:
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        return future.result()
                    except WeatherError as weather_error:
                        error = weather_error
        finally:
            for future in pending:
                future.cancel()
        assert error is not None
        raise error

    def _fetch(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        form = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "timezone": "GMT",
            "start_hour": start.strftime(TIME_FORMAT),
            "end_hour": end.strftime(TIME_FORMAT),
        }
        if self.api_key:
            form["apikey"] = self.api_key
        try:
            data = request_json(
                "POST", f"{self.base_url}/v1/forecast", service="open-meteo", data=form, timeout=REQUEST_TIMEOUT_S
            )
        except UpstreamError as exc:
            if exc.status == 429:
                raise WeatherError("The weather service's rate limit was reached. Try again in a minute.") from exc
            raise WeatherError("The weather service is unavailable. Try again in a minute.") from exc
        locations = data if isinstance(data, list) else [data]
        if len(locations) != len(points):
            raise WeatherError(INCOMPLETE_FORECAST)
        hours = int((end - start) / HOUR) + 1
        expected_times = [(start + hour * HOUR).strftime(TIME_FORMAT) for hour in range(hours)]
        for location in locations:
            hourly = location.get("hourly") or {}
            if hourly.get("time") != expected_times:
                raise WeatherError("The weather service returned an unexpected time window.")
            if any(len(hourly.get(variable) or ()) != hours for variable in HOURLY_VARIABLES):
                raise WeatherError(INCOMPLETE_FORECAST)
        return [_parse(loc["hourly"], start) for loc in locations]


def _cache_key(point: LatLon, start: datetime) -> str:
    return f"open-meteo:{point[0]:.4f},{point[1]:.4f}:{start:%Y%m%d%H}"


def _filled(values: list[float | None], default: float | None = None) -> tuple[float, ...]:
    if all(value is None for value in values):
        # A model that doesn't report a precipitation type reports none of it; missing wind or
        # temperature is unknown weather, which must not be scored as calm.
        if default is None:
            raise WeatherError(INCOMPLETE_FORECAST)
        return (default,) * len(values)
    filled: list[float] = []
    previous = next(value for value in values if value is not None)
    gap_hours = 0
    for value in values:
        if value is None:
            gap_hours += 1
            if gap_hours > MAX_FILLED_GAP_HOURS:
                raise WeatherError(INCOMPLETE_FORECAST)
        else:
            previous, gap_hours = value, 0
        filled.append(float(previous))
    return tuple(filled)


def _parse(hourly: dict, start: datetime) -> HourlySeries:
    rain = _filled(hourly["rain"], default=0.0)
    showers = _filled(hourly["showers"], default=0.0)
    return HourlySeries(
        start=start,
        wind_mph=_filled(hourly["wind_speed_10m"]),
        gust_mph=_filled(hourly["wind_gusts_10m"]),
        rain_in=tuple(r + s for r, s in zip(rain, showers)),
        snow_in=_filled(hourly["snowfall"], default=0.0),
        temp_f=_filled(hourly["temperature_2m"]),
    )
