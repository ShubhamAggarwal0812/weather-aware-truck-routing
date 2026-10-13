"""Test doubles: straight-line routes, a scripted routing provider, and scripted weather."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from itertools import pairwise

from apps.routing.providers import Route, RouteRequest
from apps.trips.domain.recommend import RouteScore
from apps.trips.domain.risk import RiskLevel
from apps.weather.forecast import HOUR, HourlySeries, floor_hour
from common.geo import METERS_PER_MILE, LatLon, cumulative_distances

MPH_TO_MPS = 0.44704


def straight_route(
    start: LatLon,
    end: LatLon,
    *,
    mph: float = 60,
    summary: str = "",
    steps: int = 200,
    via: LatLon | None = None,
    through: list[LatLon] | None = None,
) -> Route:
    """A route along straight lines (through ``via`` if given) at a constant speed."""
    legs = [start, *(through or ([via] if via else [])), end]
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


WindRainSnow = tuple[float, float, float]
ConditionsAt = Callable[[float, float, datetime], WindRainSnow]


class FakeWeather:
    """Builds hourly series from a function of place and time. Precip is the total for
    the hour ending at each timestamp, like Open-Meteo, so it's sampled mid-hour."""

    def __init__(self, conditions_at: ConditionsAt | None = None, *, gusts_and_temperature_known: bool = True):
        self.conditions_at = conditions_at or (lambda latitude, longitude, time: (5.0, 0.0, 0.0))
        self.gusts_and_temperature_known = gusts_and_temperature_known
        self.calls: list[tuple[int, datetime, datetime]] = []

    def hourly(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        self.calls.append((len(points), start, end))
        # Like the real client, so precipitation at ``end`` can read the following hour's total.
        start = floor_hour(start)
        hours = int((floor_hour(end) - start) / HOUR) + 2
        out = []
        for latitude, longitude in points:
            times = [start + hour * HOUR for hour in range(hours)]
            wind = tuple(self.conditions_at(latitude, longitude, time)[0] for time in times)
            rain = tuple(self.conditions_at(latitude, longitude, time - HOUR / 2)[1] for time in times)
            snow = tuple(self.conditions_at(latitude, longitude, time - HOUR / 2)[2] for time in times)
            gusts = wind if self.gusts_and_temperature_known else (None,) * hours
            temperature = (50.0,) * hours if self.gusts_and_temperature_known else (None,) * hours
            out.append(HourlySeries(start, wind, gusts, rain, snow, temperature))
        return out


def route_score(route_id: str, travel_hours: float = 10, **miles_by_level: float) -> RouteScore:
    levels = {level.key: level for level in RiskLevel}
    meters = {level: 0.0 for level in RiskLevel}
    for key, miles in miles_by_level.items():
        meters[levels[key]] = miles * METERS_PER_MILE
    return RouteScore(route_id, meters, travel_hours * HOUR.total_seconds())


def storm(lat, lon, t):
    """50 mph wind in a band around lon -100 south of 40.8N; calm elsewhere."""
    return (50.0, 0.0, 0.0) if -100.6 <= lon <= -99.4 and lat < 40.8 else (8.0, 0.0, 0.0)


def back_and_forth_line(south_latitude: float, north_latitude: float, legs: int = 8) -> list[LatLon]:
    points: list[LatLon] = []
    for leg in range(legs):
        longitude = -124 + leg * 54 / (legs - 1)
        ends = [(south_latitude, longitude), (north_latitude, longitude)]
        points += ends if leg % 2 == 0 else ends[::-1]
    return points
