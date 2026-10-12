"""Test doubles: straight-line routes, a scripted routing provider, and scripted weather."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from itertools import pairwise

from apps.routing.providers import Route, RouteRequest
from apps.weather.forecast import HOUR, HourlySeries, floor_hour
from common.geo import LatLon, cumulative_distances

MPH_TO_MPS = 0.44704


def straight_route(
    start: LatLon,
    end: LatLon,
    *,
    mph: float = 60,
    summary: str = "",
    steps: int = 200,
    via: LatLon | None = None,
) -> Route:
    """A route along straight lines (through ``via`` if given) at a constant speed."""
    legs = [start, via, end] if via else [start, end]
    points: list[LatLon] = []
    for a, b in pairwise(legs):
        n = steps // (len(legs) - 1)
        points.extend((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n))
    points.append(end)
    length = cumulative_distances(points)[-1]
    duration = length / (mph * MPH_TO_MPS)
    route = Route.from_timed_points(points, [], length_m=length, duration_s=duration, summary=summary, provider="fake")
    route.via = via
    return route


class FakeProvider:
    name = "fake"
    truck_aware = True

    def __init__(self, routes: list[Route], via: Callable[[LatLon], Route | None] | None = None):
        self._routes = routes
        self._via = via
        self.via_calls: list[LatLon] = []
        self.requests: list[RouteRequest] = []

    def routes(self, request: RouteRequest, *, alternatives: int) -> list[Route]:
        self.requests.append(request)
        return list(self._routes)

    def route_via(self, request: RouteRequest, via: LatLon) -> Route | None:
        self.via_calls.append(via)
        return self._via(via) if self._via else None


# conditions(lat, lon, time) -> (wind_mph, rain_in_hr, snow_in_hr)
ConditionsFn = Callable[[float, float, datetime], tuple[float, float, float]]


class FakeWeather:
    """Builds hourly series from a function of place and time. Precip is the total for
    the hour ending at each timestamp, like Open-Meteo, so it's sampled mid-hour."""

    def __init__(self, fn: ConditionsFn | None = None):
        self.fn = fn or (lambda lat, lon, t: (5.0, 0.0, 0.0))
        self.calls: list[tuple[int, datetime, datetime]] = []

    def hourly(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        start, end = floor_hour(start), floor_hour(end)
        self.calls.append((len(points), start, end))
        hours = int((end - start) / HOUR) + 1
        out = []
        for lat, lon in points:
            times = [start + h * HOUR for h in range(hours)]
            wind = tuple(self.fn(lat, lon, t)[0] for t in times)
            rain = tuple(self.fn(lat, lon, t - HOUR / 2)[1] for t in times)
            snow = tuple(self.fn(lat, lon, t - HOUR / 2)[2] for t in times)
            out.append(HourlySeries(start, wind, wind, rain, snow, tuple(50.0 for _ in times)))
        return out


def storm(lat, lon, t):
    """50 mph wind in a band around lon -100 south of 40.8N; calm elsewhere."""
    return (50.0, 0.0, 0.0) if -100.6 <= lon <= -99.4 and lat < 40.8 else (8.0, 0.0, 0.0)
