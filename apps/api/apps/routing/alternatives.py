"""Get three genuinely different routes.

Providers often return fewer alternatives than asked for, especially on short
or corridor-like trips. When that happens we push extra routes through a point
offset to either side of the fastest route and keep the ones that are distinct
and not absurdly slow.
"""

from __future__ import annotations

import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from common.geo import (
    LatLon,
    bearing_deg,
    destination_point,
    haversine_m,
    point_at_distance,
)

from .providers.base import Route, RouteRequest, RoutingProvider

WANTED_ROUTES = 3
MAX_SLOWDOWN = 1.6  # a detour may take at most 60% longer than the fastest route
SAME_ROUTE_OVERLAP = 0.85  # sharing more than this much distance counts as the same route
NEAR_M = 1_000
CELL_DEG = 0.02

# (fraction along the fastest route, side) in the order we try them.
VIA_CANDIDATES = ((0.5, 1), (0.5, -1), (0.35, 1), (0.65, -1), (0.35, -1), (0.65, 1))


class _RouteIndex:
    """Grid hash of densified route points for fast 'is this near route X' checks."""

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], list[LatLon]] = defaultdict(list)

    def add(self, route: Route, step_m: float = 500) -> None:
        d = 0.0
        while d <= route.distance_m:
            p = point_at_distance(route.points, route.cum_distance_m, d)
            self.cells[_cell(p)].append(p)
            d += step_m

    def near(self, p: LatLon) -> bool:
        cr, cc = _cell(p)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for q in self.cells.get((cr + dr, cc + dc), ()):
                    if haversine_m(p, q) <= NEAR_M:
                        return True
        return False


def _cell(p: LatLon) -> tuple[int, int]:
    return (math.floor(p[0] / CELL_DEG), math.floor(p[1] / CELL_DEG))


def overlap_fraction(route: Route, index: _RouteIndex, step_m: float = 2_000) -> float:
    """Share of ``route``'s length that runs within 1 km of the indexed routes."""
    samples = max(2, int(route.distance_m // step_m) + 1)
    near = sum(
        index.near(point_at_distance(route.points, route.cum_distance_m, route.distance_m * i / (samples - 1)))
        for i in range(samples)
    )
    return near / samples


def distinct_routes(routes: list[Route], limit: int) -> list[Route]:
    """Keep routes in order, dropping any that mostly retrace the ones already kept."""
    kept: list[Route] = []
    for route in routes:
        if not kept or _overlap_with(route, kept) < SAME_ROUTE_OVERLAP:
            kept.append(route)
        if len(kept) == limit:
            break
    return kept


def _overlap_with(route: Route, others: list[Route]) -> float:
    index = _RouteIndex()
    for other in others:
        index.add(other)
    return overlap_fraction(route, index)


def via_points(fastest: Route, request: RouteRequest) -> list[LatLon]:
    """Points to the left and right of the fastest route, scaled to trip length."""
    crow = haversine_m(request.origin, request.destination)
    offset = min(150_000, max(20_000, 0.15 * crow))
    out = []
    for fraction, side in VIA_CANDIDATES:
        d = fastest.distance_m * fraction
        a = point_at_distance(fastest.points, fastest.cum_distance_m, max(0.0, d - 2_000))
        b = point_at_distance(fastest.points, fastest.cum_distance_m, min(fastest.distance_m, d + 2_000))
        mid = point_at_distance(fastest.points, fastest.cum_distance_m, d)
        out.append(destination_point(mid, bearing_deg(a, b) + 90 * side, offset))
    return out


def three_routes(provider: RoutingProvider, request: RouteRequest) -> list[Route]:
    routes = distinct_routes(provider.routes(request, alternatives=WANTED_ROUTES - 1), WANTED_ROUTES)
    if not routes:
        return routes

    fastest = routes[0]
    vias = via_points(fastest, request)
    # Two rounds keep provider calls (and free-tier quota) down when the first round is enough.
    for batch in (vias[:4], vias[4:]):
        if len(routes) >= WANTED_ROUTES:
            break
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            candidates = list(pool.map(lambda via: provider.route_via(request, via), batch))
        for candidate in candidates:
            if len(routes) >= WANTED_ROUTES:
                break
            if candidate is None or candidate.drive_s > fastest.drive_s * MAX_SLOWDOWN:
                continue
            if _overlap_with(candidate, routes) < SAME_ROUTE_OVERLAP:
                candidate.notes.append("Detour alternative: the routing API returned fewer than 3 routes.")
                routes.append(candidate)
    return routes
