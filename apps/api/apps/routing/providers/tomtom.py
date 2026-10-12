"""TomTom Routing API in truck mode: weight-aware roads and truck travel times."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.routing.exceptions import RoutingError
from common.geo import LatLon, cumulative_distances
from common.http import UpstreamError, request_json

from .base import Route, RouteRequest

BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
LB_TO_KG = 0.45359237
VIA_RADIUS_M = 15_000
# Without a cap TomTom's truck mode runs at car speeds (~73 mph average on I-80).
# 65 mph is a common fleet speed-governor setting.
TRUCK_MAX_SPEED_KMH = 105


class TomTomProvider:
    name = "tomtom"
    truck_aware = True

    def __init__(self, api_key: str):
        self.api_key = api_key

    def routes(self, request: RouteRequest, *, alternatives: int) -> list[Route]:
        locations = [request.origin, request.destination]
        data = self._calculate(locations, request, alternatives=alternatives)
        return [self._parse(r) for r in data.get("routes", [])]

    def route_via(self, request: RouteRequest, via: LatLon) -> Route | None:
        try:
            data = self._calculate([request.origin, via, request.destination], request, alternatives=0, circle=True)
        except RoutingError:
            return None
        routes = data.get("routes") or []
        if not routes:
            return None
        route = self._parse(routes[0])
        route.via = via
        return route

    def _calculate(
        self, locations: list[LatLon], request: RouteRequest, *, alternatives: int, circle: bool = False
    ) -> dict[str, Any]:
        parts = []
        for i, (lat, lon) in enumerate(locations):
            is_via = 0 < i < len(locations) - 1
            parts.append(f"circle({lat:.5f},{lon:.5f},{VIA_RADIUS_M})" if circle and is_via else f"{lat:.5f},{lon:.5f}")
        params: list[tuple[str, str | int]] = [
            ("key", self.api_key),
            ("travelMode", "truck"),
            ("vehicleCommercial", "true"),
            ("vehicleMaxSpeed", TRUCK_MAX_SPEED_KMH),
            ("vehicleWeight", round(request.gross_weight_lb * LB_TO_KG)),
            ("routeType", "fastest"),
            ("traffic", "true"),
            ("departAt", _depart_param(request.depart_at)),
            ("maxAlternatives", alternatives),
            ("routeRepresentation", "polyline"),
            ("extendedRouteRepresentation", "distance"),
            ("extendedRouteRepresentation", "travelTime"),
            ("sectionType", "importantRoadStretch"),
        ]
        if alternatives:
            # TomTom rejects alternativeType unless maxAlternatives > 0.
            params.append(("alternativeType", "anyRoute"))
        try:
            return request_json("GET", f"{BASE_URL}/{':'.join(parts)}/json", service="tomtom", params=params)
        except UpstreamError as exc:
            raise _routing_error(exc) from exc

    def _parse(self, raw: dict[str, Any]) -> Route:
        points: list[LatLon] = [(p["latitude"], p["longitude"]) for leg in raw["legs"] for p in leg["points"]]
        summary = raw["summary"]
        timed = [(p["pointIndex"], p["travelTimeInSeconds"]) for p in raw.get("progress", []) if "pointIndex" in p]
        return Route.from_timed_points(
            points,
            timed,
            length_m=float(summary["lengthInMeters"]),
            duration_s=float(summary["travelTimeInSeconds"]),
            summary=_road_summary(points, raw.get("sections", [])),
            provider=self.name,
        )


def _depart_param(depart_at: datetime) -> str:
    # TomTom rejects departure times in the past; anything within a minute is "now".
    if depart_at <= datetime.now(UTC) + timedelta(minutes=1):
        return "now"
    return depart_at.astimezone(UTC).isoformat(timespec="seconds")


def _road_summary(points: list[LatLon], sections: list[dict[str, Any]]) -> str:
    """'via I-80, I-76': the two road numbers the route spends the most distance on."""
    cum = cumulative_distances(points)
    length: dict[str, float] = defaultdict(float)
    for section in sections:
        if section.get("sectionType") != "IMPORTANT_ROAD_STRETCH":
            continue
        numbers = [n.get("text") for n in section.get("roadNumbers", []) if n.get("text")]
        name = numbers[0] if numbers else (section.get("streetName") or {}).get("text")
        if not name:
            continue
        start, end = section["startPointIndex"], section["endPointIndex"]
        length[name] += cum[min(end, len(cum) - 1)] - cum[min(start, len(cum) - 1)]
    top = sorted(length, key=lambda name: length[name], reverse=True)[:2]
    return f"via {', '.join(top)}" if top else ""


def _routing_error(exc: UpstreamError) -> RoutingError:
    body = exc.body.upper()
    if "NO_ROUTE_FOUND" in body or "CANNOT_FIND_PATH" in body or "MAP_MATCHING_FAILURE" in body:
        return RoutingError("No truck route was found between these places.", status=422)
    if exc.status in (401, 403):
        return RoutingError("The routing service rejected the API key.")
    if exc.status == 429:
        return RoutingError("The routing service's free quota is used up for now. Try again later.", status=503)
    return RoutingError("The routing service is unavailable. Try again in a minute.")
