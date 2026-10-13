"""Trip planning: routes -> checkpoints with ETAs -> weather at each ETA -> risk -> ranking.

The result is a :class:`TripPlan` of plain dataclasses; ``presenters`` turns it into
the API response.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.routing.alternatives import three_routes
from apps.routing.exceptions import RoutingError
from apps.routing.providers import Route, RouteRequest, RoutingProvider
from apps.trips.domain import hos
from apps.trips.domain.checkpoints import Placement, place_checkpoints
from apps.trips.domain.recommend import Comparison, RouteScore, recommend
from apps.trips.domain.risk import Assessment, Conditions, RiskLevel, assess
from apps.weather.forecast import ForecastSource, Sample
from common.geo import LatLon, point_at_distance

# Load weight is cargo; routing needs the whole truck. 35,000 lb is a typical
# empty tractor + 53 ft dry van.
TARE_WEIGHT_LB = 35_000
# ~5 km: close to the 3 km HRRR grid, and it lets overlapping routes share forecasts.
CHECKPOINT_SNAP_DEG = 0.05


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    label: str = ""

    @property
    def point(self) -> LatLon:
        return (self.lat, self.lon)


@dataclass(frozen=True)
class TripInput:
    origin: Place
    destination: Place
    departure: datetime
    load_weight_lb: int
    interval_miles: int
    rest_breaks: bool = True

    @property
    def gross_weight_lb(self) -> int:
        return TARE_WEIGHT_LB + self.load_weight_lb


@dataclass
class PlannedCheckpoint:
    placement: Placement
    position: LatLon
    drive_s: float
    eta: datetime
    sample: Sample | None = None
    assessment: Assessment | None = None


@dataclass
class PlannedRoute:
    id: str
    route: Route
    checkpoints: list[PlannedCheckpoint]
    travel_s: float

    @property
    def arrival(self) -> datetime:
        return self.checkpoints[-1].eta


@dataclass(frozen=True)
class TripPlan:
    trip: TripInput
    provider: RoutingProvider
    routes: list[PlannedRoute]
    scores: dict[str, RouteScore]
    ranking: list[RouteScore]
    comparisons: list[Comparison]

    @property
    def best(self) -> RouteScore:
        return self.ranking[0]


def plan_trip(trip: TripInput, provider: RoutingProvider, weather: ForecastSource) -> TripPlan:
    request = RouteRequest(
        origin=trip.origin.point,
        destination=trip.destination.point,
        depart_at=trip.departure,
        gross_weight_lb=trip.gross_weight_lb,
    )
    routes = three_routes(provider, request)
    if not routes:
        raise RoutingError("No route was found between these places.", status=422)

    planned = [_place_checkpoints(chr(ord("A") + i), route, trip) for i, route in enumerate(routes)]
    _attach_weather(planned, trip, weather)

    scores = {p.id: _score(p) for p in planned}
    ranking, comparisons = recommend(list(scores.values()))
    return TripPlan(trip, provider, planned, scores, ranking, comparisons)


def _place_checkpoints(route_id: str, route: Route, trip: TripInput) -> PlannedRoute:
    checkpoints = []
    for placement in place_checkpoints(route.distance_m, trip.interval_miles):
        drive_s = route.drive_s_at(placement.distance_m)
        eta = trip.departure + timedelta(seconds=hos.elapsed_s(drive_s, breaks=trip.rest_breaks))
        position = point_at_distance(route.points, route.cum_distance_m, placement.distance_m)
        checkpoints.append(PlannedCheckpoint(placement, position, drive_s, eta))
    travel_s = hos.elapsed_s(route.drive_s, breaks=trip.rest_breaks)
    return PlannedRoute(route_id, route, checkpoints, travel_s)


def _snap(p: LatLon) -> LatLon:
    step = CHECKPOINT_SNAP_DEG
    return (round(round(p[0] / step) * step, 4), round(round(p[1] / step) * step, 4))


def _attach_weather(planned: list[PlannedRoute], trip: TripInput, weather: ForecastSource) -> None:
    """One batched forecast fetch for every checkpoint on every route."""
    snapped = sorted({_snap(checkpoint.position) for route in planned for checkpoint in route.checkpoints})
    latest_arrival = max(route.arrival for route in planned)
    by_point = dict(zip(snapped, weather.hourly(snapped, trip.departure, latest_arrival)))
    for route in planned:
        for checkpoint in route.checkpoints:
            checkpoint.sample = by_point[_snap(checkpoint.position)].at(checkpoint.eta)
            checkpoint.assessment = assess(conditions(checkpoint.sample), trip.load_weight_lb)


def conditions(sample: Sample) -> Conditions:
    """The three conditions the risk rules score."""
    return Conditions(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr)


def _score(p: PlannedRoute) -> RouteScore:
    meters: dict[RiskLevel, float] = defaultdict(float)
    for cp in p.checkpoints:
        assert cp.assessment is not None
        meters[cp.assessment.level] += cp.placement.covered_m
    return RouteScore(p.id, {level: meters.get(level, 0.0) for level in RiskLevel}, p.travel_s)
