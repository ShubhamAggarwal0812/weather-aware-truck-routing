"""OSRM fallback for running without a TomTom key.

The public demo server only has a car profile, so travel times are car times and
weight limits are ignored. The API response says so, and the UI shows a notice.
"""

from __future__ import annotations

from itertools import accumulate
from typing import Any

from trips.domain.geo import LatLon
from trips.services.http import UpstreamError, request_json

from .base import Route, RouteRequest, RoutingError


class OSRMProvider:
    name = "osrm"
    truck_aware = False

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def routes(self, request: RouteRequest, *, alternatives: int) -> list[Route]:
        data = self._route([request.origin, request.destination], alternatives=alternatives)
        return [self._parse(r) for r in data["routes"]]

    def route_via(self, request: RouteRequest, via: LatLon) -> Route | None:
        try:
            data = self._route([request.origin, via, request.destination], alternatives=0)
        except RoutingError:
            return None
        if not data.get("routes"):
            return None
        route = self._parse(data["routes"][0])
        route.via = via
        return route

    def _route(self, locations: list[LatLon], *, alternatives: int) -> dict[str, Any]:
        coords = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in locations)
        params = {
            "alternatives": str(alternatives) if alternatives else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "true",  # leg summaries (road names) are only filled in with steps
            "continue_straight": "true",
        }
        try:
            data = request_json("GET", f"{self.base_url}/route/v1/driving/{coords}", service="osrm", params=params)
        except UpstreamError as exc:
            if exc.status == 400 and "NoRoute" in exc.body:
                raise RoutingError("No route was found between these places.", status=422) from exc
            raise RoutingError("The routing service is unavailable. Try again in a minute.") from exc
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RoutingError("No route was found between these places.", status=422)
        return data

    def _parse(self, raw: dict[str, Any]) -> Route:
        points: list[LatLon] = [(lat, lon) for lon, lat in raw["geometry"]["coordinates"]]
        # annotation[i] is the segment from coordinate i to i+1, across all legs.
        durations = [d for leg in raw["legs"] for d in leg["annotation"]["duration"]]
        timed = list(enumerate(accumulate(durations, initial=0.0))) if len(durations) == len(points) - 1 else []
        names = list(dict.fromkeys(n.strip() for leg in raw["legs"] for n in leg.get("summary", "").split(",")))
        names = [n for n in names if n][:2]
        return Route.from_timed_points(
            points,
            timed,
            length_m=float(raw["distance"]),
            duration_s=float(raw["duration"]),
            summary=f"via {', '.join(names)}" if names else "",
            provider=self.name,
        )
