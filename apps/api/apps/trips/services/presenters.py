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


def _checkpoint(cp: PlannedCheckpoint) -> dict[str, Any]:
    assert cp.sample is not None and cp.assessment is not None
    s = cp.sample
    return {
        "index": cp.placement.index,
        "mile": _mi(cp.placement.distance_m),
        "covers_mi": [_mi(cp.placement.covers_from_m), _mi(cp.placement.covers_to_m)],
        "lat": round(cp.position[0], 5),
        "lon": round(cp.position[1], 5),
        "eta": iso(cp.eta),
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
    fastest = min(plan.routes, key=lambda p: p.travel_s).id
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
        "reasons": [_reason(best.route_id, c) for c in plan.comparisons],
        "comparisons": [
            {
                "route_id": c.route_id,
                "criterion": c.criterion,
                "recommended_value": c.recommended_value,
                "other_value": c.other_value,
            }
            for c in plan.comparisons
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
