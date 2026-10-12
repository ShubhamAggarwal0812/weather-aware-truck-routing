"""Trip planning: routes -> checkpoints with ETAs -> weather at each ETA -> risk -> ranking."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings

from trips.domain import hos
from trips.domain.checkpoints import Placement, place_checkpoints
from trips.domain.corridor import corridor_grid
from trips.domain.geo import METERS_PER_MILE, LatLon, point_at_distance, simplify, slice_polyline
from trips.domain.recommend import Comparison, RouteScore, compare, rank
from trips.domain.risk import Assessment, RiskLevel, assess, rules_table

from .routing.alternatives import three_routes
from .routing.base import Route, RouteRequest, RoutingError, RoutingProvider
from .routing.osrm import OSRMProvider
from .routing.tomtom import TomTomProvider
from .weather import HOUR, OpenMeteoClient, Sample, WeatherError, floor_hour, forecast_limit

# Load weight is cargo; routing needs the whole truck. 35,000 lb is a typical
# empty tractor + 53 ft dry van.
TARE_WEIGHT_LB = 35_000
HEATMAP_HOURS = 48
POSITION_STEP = timedelta(minutes=15)
CHECKPOINT_SNAP_DEG = 0.02  # ~2 km; finer than the 3 km weather model grid
SEGMENT_TOLERANCE_M = 30
CORRIDOR_LINE_TOLERANCE_M = 2_000

# Truck position codes in Route.positions.
WAITING, DRIVING, BREAK, REST, ARRIVED = range(5)
_ACTIVITY_CODES = {"driving": DRIVING, "break": BREAK, "rest": REST}


def routing_provider() -> RoutingProvider:
    if settings.ROUTING_PROVIDER == "tomtom" and settings.TOMTOM_API_KEY:
        return TomTomProvider(settings.TOMTOM_API_KEY)
    return OSRMProvider(settings.OSRM_BASE_URL)


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


@dataclass
class _Checkpoint:
    placement: Placement
    position: LatLon
    drive_s: float
    eta: datetime
    sample: Sample | None = None
    assessment: Assessment | None = None


@dataclass
class _PlannedRoute:
    id: str
    route: Route
    checkpoints: list[_Checkpoint]
    travel_s: float

    @property
    def arrival(self) -> datetime:
        return self.checkpoints[-1].eta


def plan_trip(trip: TripInput, provider: RoutingProvider, weather: OpenMeteoClient) -> dict[str, Any]:
    request = RouteRequest(
        origin=trip.origin.point,
        destination=trip.destination.point,
        depart_at=trip.departure,
        gross_weight_lb=TARE_WEIGHT_LB + trip.load_weight_lb,
    )
    routes = three_routes(provider, request)
    if not routes:
        raise RoutingError("No route was found between these places.", status=422)

    planned = [_place(chr(ord("A") + i), route, trip) for i, route in enumerate(routes)]
    latest_eta = max(p.arrival for p in planned)
    if latest_eta > forecast_limit():
        raise WeatherError("This trip ends beyond the 16-day forecast. Choose an earlier departure.")
    _attach_weather(planned, trip, weather)

    scores = {p.id: _score(p) for p in planned}
    ranking = rank(list(scores.values()))
    best = ranking[0]
    comparisons = [compare(best, other) for other in ranking[1:]]
    order = {score.route_id: i + 1 for i, score in enumerate(ranking)}

    return {
        "provider": {"name": provider.name, "truck_aware": provider.truck_aware},
        "departure": _iso(trip.departure),
        "load_weight_lb": trip.load_weight_lb,
        "gross_weight_lb": request.gross_weight_lb,
        "interval_miles": trip.interval_miles,
        "rest_breaks": trip.rest_breaks,
        "heatmap_start": _iso(floor_hour(trip.departure)),
        "routes": [_route_json(p, scores[p.id], order[p.id], trip) for p in planned],
        "recommendation": _recommendation_json(best, comparisons, planned),
        "rules": rules_table(),
    }


def corridor_forecast(
    lines: list[list[LatLon]], departure: datetime, load_weight_lb: int, weather: OpenMeteoClient
) -> dict[str, Any]:
    """Hourly weather and risk on a grid around the routes, for hours 0..48 after departure."""
    grid = corridor_grid(lines)
    start = floor_hour(departure)
    hours = HEATMAP_HOURS + 1
    if start + hours * HOUR > forecast_limit():
        raise WeatherError("The heatmap window runs past the 16-day forecast. Choose an earlier departure.")
    # One extra hour so the last hour's precipitation total is available.
    series = weather.hourly(grid.centers, start, start + hours * HOUR) if grid.cells else []
    wind, rain, snow, risk = [], [], [], []
    for h in range(hours):
        samples = [s.hour(h) for s in series]
        wind.append([round(s.wind_mph, 1) for s in samples])
        rain.append([round(s.rain_in_hr, 3) for s in samples])
        snow.append([round(s.snow_in_hr, 3) for s in samples])
        risk.append([int(assess(s.conditions, load_weight_lb).level) for s in samples])
    return {
        "step_deg": grid.step_deg,
        "rows": [r for r, _ in grid.cells],
        "cols": [c for _, c in grid.cells],
        "times": [_iso(start + h * HOUR) for h in range(hours)],
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
        "risk": risk,
    }


def _place(route_id: str, route: Route, trip: TripInput) -> _PlannedRoute:
    checkpoints = []
    for placement in place_checkpoints(route.distance_m, trip.interval_miles):
        drive_s = route.drive_s_at(placement.distance_m)
        eta = trip.departure + timedelta(seconds=hos.elapsed_s(drive_s, breaks=trip.rest_breaks))
        position = point_at_distance(route.points, route.cum_distance_m, placement.distance_m)
        checkpoints.append(_Checkpoint(placement, position, drive_s, eta))
    travel_s = hos.elapsed_s(route.drive_s, breaks=trip.rest_breaks)
    return _PlannedRoute(route_id, route, checkpoints, travel_s)


def _snap(p: LatLon) -> LatLon:
    return (
        round(round(p[0] / CHECKPOINT_SNAP_DEG) * CHECKPOINT_SNAP_DEG, 4),
        round(round(p[1] / CHECKPOINT_SNAP_DEG) * CHECKPOINT_SNAP_DEG, 4),
    )


def _attach_weather(planned: list[_PlannedRoute], trip: TripInput, weather: OpenMeteoClient) -> None:
    """One batched forecast fetch for every checkpoint on every route."""
    snapped = sorted({_snap(cp.position) for p in planned for cp in p.checkpoints})
    start = floor_hour(trip.departure)
    end = floor_hour(max(p.arrival for p in planned)) + HOUR
    by_point = dict(zip(snapped, weather.hourly(snapped, start, end)))
    for p in planned:
        for cp in p.checkpoints:
            cp.sample = by_point[_snap(cp.position)].at(cp.eta)
            cp.assessment = assess(cp.sample.conditions, trip.load_weight_lb)


def _score(p: _PlannedRoute) -> RouteScore:
    meters: dict[RiskLevel, float] = defaultdict(float)
    for cp in p.checkpoints:
        assert cp.assessment is not None
        meters[cp.assessment.level] += cp.placement.covered_m
    return RouteScore(p.id, {level: meters.get(level, 0.0) for level in RiskLevel}, p.travel_s)


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mi(meters: float) -> float:
    return round(meters / METERS_PER_MILE, 1)


def _route_json(p: _PlannedRoute, score: RouteScore, rank_position: int, trip: TripInput) -> dict[str, Any]:
    route = p.route
    levels = [cp.assessment.level for cp in p.checkpoints if cp.assessment]
    return {
        "id": p.id,
        "summary": route.summary,
        "rank": rank_position,
        "recommended": rank_position == 1,
        "distance_mi": _mi(route.distance_m),
        "drive_time_s": round(route.drive_s),
        "travel_time_s": round(p.travel_s),
        "arrival": _iso(p.arrival),
        "notes": route.notes,
        "risk": {
            "miles_by_level": {level.key: _mi(score.meters_by_level[level]) for level in RiskLevel},
            "average": round(score.average_risk, 3),
            "max_level": max(levels).key if levels else RiskLevel.LOW.key,
        },
        "checkpoints": [_checkpoint_json(cp) for cp in p.checkpoints],
        "segments": [
            {
                "checkpoint": cp.placement.index,
                "level": cp.assessment.level.key if cp.assessment else None,
                "coordinates": [
                    [round(lon, 5), round(lat, 5)]
                    for lat, lon in simplify(
                        slice_polyline(
                            route.points, route.cum_distance_m, cp.placement.covers_from_m, cp.placement.covers_to_m
                        ),
                        SEGMENT_TOLERANCE_M,
                    )
                ],
            }
            for cp in p.checkpoints
            if cp.placement.covered_m > 0
        ],
        "stops": [_stop_json(stop, route, trip) for stop in hos.stops(route.drive_s, breaks=trip.rest_breaks)],
        "positions": _positions(route, trip),
        "corridor_line": [
            [round(lat, 4), round(lon, 4)] for lat, lon in simplify(route.points, CORRIDOR_LINE_TOLERANCE_M)
        ],
    }


def _checkpoint_json(cp: _Checkpoint) -> dict[str, Any]:
    assert cp.sample is not None and cp.assessment is not None
    s = cp.sample
    return {
        "index": cp.placement.index,
        "mile": _mi(cp.placement.distance_m),
        "covers_mi": [_mi(cp.placement.covers_from_m), _mi(cp.placement.covers_to_m)],
        "lat": round(cp.position[0], 5),
        "lon": round(cp.position[1], 5),
        "eta": _iso(cp.eta),
        "drive_time_s": round(cp.drive_s),
        "level": cp.assessment.level.key,
        "conditions": {
            "wind_mph": round(s.wind_mph, 1),
            "gust_mph": round(s.gust_mph, 1),
            "rain_in_hr": round(s.rain_in_hr, 3),
            "snow_in_hr": round(s.snow_in_hr, 3),
            "temp_f": round(s.temp_f),
        },
        "factors": [
            {"condition": f.condition, "level": f.level.key, "load_rule": f.load_rule} for f in cp.assessment.factors
        ],
        "drivers": [f.condition for f in cp.assessment.drivers],
    }


def _stop_json(stop: hos.Stop, route: Route, trip: TripInput) -> dict[str, Any]:
    distance = route.distance_at(stop.drive_s)
    lat, lon = point_at_distance(route.points, route.cum_distance_m, distance)
    start = trip.departure + timedelta(seconds=stop.start_elapsed_s)
    return {
        "kind": stop.kind,
        "mile": _mi(distance),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "start": _iso(start),
        "end": _iso(start + timedelta(seconds=stop.duration_s)),
    }


def _positions(route: Route, trip: TripInput) -> list[list[float]]:
    """Where the truck is every 15 minutes across the heatmap window: [lat, lon, status]."""
    start = floor_hour(trip.departure)
    steps = int(timedelta(hours=HEATMAP_HOURS) / POSITION_STEP) + 1
    out = []
    for k in range(steps):
        elapsed = (start + k * POSITION_STEP - trip.departure).total_seconds()
        if elapsed < 0:
            code, distance = WAITING, 0.0
        else:
            drive, activity = hos.drive_s_at(elapsed, breaks=trip.rest_breaks)
            if drive >= route.drive_s:
                code, distance = ARRIVED, route.distance_m
            else:
                code, distance = _ACTIVITY_CODES[activity], route.distance_at(drive)
        lat, lon = point_at_distance(route.points, route.cum_distance_m, distance)
        out.append([round(lat, 4), round(lon, 4), code])
    return out


def _recommendation_json(best: RouteScore, comparisons: list[Comparison], planned: list[_PlannedRoute]) -> dict:
    safe = best.miles(RiskLevel.NO_TRAVEL) == 0
    fastest = min(planned, key=lambda p: p.travel_s).id
    if not safe:
        headline = (
            f"No route is safe at this departure time. Route {best.route_id} has the least No Travel "
            "exposure; consider waiting for conditions to clear."
        )
    elif fastest == best.route_id:
        headline = f"Route {best.route_id} is the safest and the fastest option."
    else:
        headline = f"Route {best.route_id} is the safest option."
    return {
        "route_id": best.route_id,
        "safe": safe,
        "headline": headline,
        "reasons": [_reason(best.route_id, c) for c in comparisons],
        "comparisons": [
            {
                "route_id": c.route_id,
                "criterion": c.criterion,
                "recommended_value": c.recommended_value,
                "other_value": c.other_value,
            }
            for c in comparisons
        ],
    }


def _reason(best_id: str, c: Comparison) -> str:
    a, b, other = c.recommended_value, c.other_value, c.route_id
    if c.criterion == "no_travel_miles":
        return f"Fewer No Travel miles than Route {other} ({a:g} vs {b:g} mi)."
    if c.criterion == "severe_miles":
        return f"Fewer Severe miles than Route {other} ({a:g} vs {b:g} mi)."
    if c.criterion == "high_miles":
        return f"Same Severe mileage as Route {other}, fewer High miles ({a:g} vs {b:g} mi)."
    if c.criterion == "average_risk":
        return f"Same Severe and High mileage as Route {other}, lower average risk ({a:.2f} vs {b:.2f})."
    if c.criterion == "travel_time":
        return f"Same weather risk as Route {other} and {_duration(b - a)} faster."
    return f"Ties with Route {other} on every criterion; Route {best_id} comes first in the provider's order."


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"
