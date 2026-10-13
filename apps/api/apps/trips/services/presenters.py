"""TripPlan -> API response.

Responses are built as plain dicts: a cross-country plan holds thousands of
coordinates, and running them through DRF serializer fields is slow. The shapes
are declared in ``apps.trips.api.serializers`` (which produce the OpenAPI schema),
and a contract test checks that what's built here matches them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from apps.routing.providers import Route
from apps.trips.domain import hos
from apps.trips.domain.recommend import Comparison, RouteScore
from apps.trips.domain.risk import RiskLevel, rules_table
from apps.weather.forecast import floor_hour
from common.geo import METERS_PER_MILE, point_at_distance, simplify, slice_polyline

from .planning import PlannedCheckpoint, PlannedRoute, TripInput, TripPlan

HEATMAP_HOURS = 48
POSITION_STEP = timedelta(minutes=15)
SEGMENT_TOLERANCE_M = 30
CORRIDOR_LINE_TOLERANCE_M = 2_000

# Truck position status codes in "positions".
WAITING, DRIVING, BREAK, REST, ARRIVED = range(5)
_ACTIVITY_CODES = {"driving": DRIVING, "break": BREAK, "rest": REST}


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mi(meters: float) -> float:
    return round(meters / METERS_PER_MILE, 1)


def present_plan(plan: TripPlan) -> dict[str, Any]:
    trip = plan.trip
    order = {score.route_id: i + 1 for i, score in enumerate(plan.ranking)}
    return {
        "provider": {"name": plan.provider.name, "truck_aware": plan.provider.truck_aware},
        "departure": iso(trip.departure),
        "load_weight_lb": trip.load_weight_lb,
        "gross_weight_lb": trip.gross_weight_lb,
        "interval_miles": trip.interval_miles,
        "rest_breaks": trip.rest_breaks,
        "heatmap_start": iso(floor_hour(trip.departure)),
        "routes": [_route(p, plan.scores[p.id], order[p.id], trip) for p in plan.routes],
        "recommendation": _recommendation(plan),
        "rules": rules_table(),
    }


def _route(p: PlannedRoute, score: RouteScore, rank_position: int, trip: TripInput) -> dict[str, Any]:
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
        "arrival": iso(p.arrival),
        "notes": route.notes,
        "risk": {
            "miles_by_level": {level.key: _mi(score.meters_by_level[level]) for level in RiskLevel},
            "average": round(score.average_risk, 3),
            "max_level": max(levels).key if levels else RiskLevel.LOW.key,
        },
        "checkpoints": [_checkpoint(cp) for cp in p.checkpoints],
        "segments": [_segment(cp, route) for cp in p.checkpoints if cp.placement.covered_m > 0],
        "stops": [_stop(stop, route, trip) for stop in hos.stops(route.drive_s, breaks=trip.rest_breaks)],
        "positions": _positions(route, trip),
        "corridor_line": [
            [round(lat, 4), round(lon, 4)] for lat, lon in simplify(route.points, CORRIDOR_LINE_TOLERANCE_M)
        ],
    }


def _segment(cp: PlannedCheckpoint, route: Route) -> dict[str, Any]:
    """The stretch of road a checkpoint stands for, as a [lon, lat] line coloured by its risk."""
    assert cp.assessment is not None
    line = slice_polyline(route.points, route.cum_distance_m, cp.placement.covers_from_m, cp.placement.covers_to_m)
    return {
        "checkpoint": cp.placement.index,
        "level": cp.assessment.level.key,
        "coordinates": [[round(lon, 5), round(lat, 5)] for lat, lon in simplify(line, SEGMENT_TOLERANCE_M)],
    }


def _checkpoint(checkpoint: PlannedCheckpoint) -> dict[str, Any]:
    assert checkpoint.sample is not None and checkpoint.assessment is not None
    sample, placement = checkpoint.sample, checkpoint.placement
    return {
        "index": placement.index,
        "mile": _mi(placement.distance_m),
        "covers_mi": [_mi(placement.covers_from_m), _mi(placement.covers_to_m)],
        "lat": round(checkpoint.position[0], 5),
        "lon": round(checkpoint.position[1], 5),
        "eta": iso(checkpoint.eta),
        "drive_time_s": round(checkpoint.drive_s),
        "level": checkpoint.assessment.level.key,
        "conditions": {
            "wind_mph": round(sample.wind_mph, 1),
            "gust_mph": None if sample.gust_mph is None else round(sample.gust_mph, 1),
            "rain_in_hr": round(sample.rain_in_hr, 3),
            "snow_in_hr": round(sample.snow_in_hr, 3),
            "temp_f": None if sample.temp_f is None else round(sample.temp_f),
        },
        "factors": [
            {"condition": factor.condition, "level": factor.level.key, "load_rule": factor.load_rule}
            for factor in checkpoint.assessment.factors
        ],
        "drivers": [factor.condition for factor in checkpoint.assessment.drivers],
    }


def _stop(stop: hos.Stop, route: Route, trip: TripInput) -> dict[str, Any]:
    distance = route.distance_at(stop.drive_s)
    lat, lon = point_at_distance(route.points, route.cum_distance_m, distance)
    start = trip.departure + timedelta(seconds=stop.start_elapsed_s)
    return {
        "kind": stop.kind,
        "mile": _mi(distance),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "start": iso(start),
        "end": iso(start + timedelta(seconds=stop.duration_s)),
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


def _recommendation(plan: TripPlan) -> dict[str, Any]:
    best = plan.best
    safe = best.miles(RiskLevel.NO_TRAVEL) == 0
    fastest = min(plan.routes, key=lambda route: route.travel_s).id
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
        "reasons": [_reason(best.route_id, comparison) for comparison in plan.comparisons],
        "comparisons": [
            {
                "route_id": comparison.route_id,
                "criterion": comparison.criterion,
                "value": round(comparison.value, _COMPARISON_PLACES[comparison.criterion]),
                "leader_id": comparison.leader_id,
                "leader_value": round(comparison.leader_value, _COMPARISON_PLACES[comparison.criterion]),
            }
            for comparison in plan.comparisons
        ],
    }


# Any No Travel at all decides the ranking, so even a sliver of it keeps a digit.
_COMPARISON_PLACES = {
    "no_travel_miles": 3,
    "severe_miles": 2,
    "high_miles": 2,
    "average_risk": 3,
    "travel_time": 0,
    "tie": 0,
}
_LEVEL_NAMES = {"no_travel_miles": "No Travel", "severe_miles": "Severe", "high_miles": "High"}


def _reason(recommended_id: str, comparison: Comparison) -> str:
    other, leader = comparison.route_id, comparison.leader_id
    value, leader_value = comparison.value, comparison.leader_value
    if comparison.criterion == "tie":
        return (
            f"Ties with Route {other} on every criterion; Route {recommended_id} comes first in the provider's order."
        )
    if comparison.criterion == "travel_time":
        gap = _duration(value - leader_value)
        if leader == recommended_id:
            return f"Same weather risk as Route {other} and {gap} faster."
        return f"Route {other} has the same weather risk as Route {leader} but takes {gap} longer."
    if comparison.criterion == "average_risk":
        if leader == recommended_id:
            return (
                f"Same Severe and High mileage as Route {other}, "
                f"lower average risk ({leader_value:.2f} vs {value:.2f})."
            )
        return f"Route {other} has a higher average risk than Route {leader} ({value:.2f} vs {leader_value:.2f})."
    level = _LEVEL_NAMES[comparison.criterion]
    if leader != recommended_id:
        return (
            f"Route {other} has more {level} miles than Route {leader} ({_miles(value)} vs {_miles(leader_value)} mi)."
        )
    values = f"({_miles(leader_value)} vs {_miles(value)} mi)"
    if comparison.criterion == "high_miles":
        return f"Same Severe mileage as Route {other}, fewer High miles {values}."
    return f"Fewer {level} miles than Route {other} {values}."


def _miles(value: float) -> str:
    # A sliver of No Travel decides the ranking, so it must not print as 0.
    return "under 0.01" if 0 < value < 0.005 else f"{round(value, 2):g}"


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"
