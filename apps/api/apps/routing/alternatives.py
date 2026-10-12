"""Get three genuinely different routes.

Providers often return fewer alternatives than asked for (TomTom returns none
for most future departures). Extra routes are forced through points offset to
either side of the trip and kept only if they are distinct and not absurdly slow.
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


def detour_points(origin: LatLon, destination: LatLon, fractions: tuple[float, ...] = (0.5,)) -> list[LatLon]:
    """Points either side of the straight line between the endpoints, scaled to trip length.

    They only depend on the endpoints, so detour requests can go out together
    with the main request instead of waiting for it.
    """
    crow = haversine_m(origin, destination)
    offset = min(150_000, max(20_000, 0.15 * crow))
    bearing = bearing_deg(origin, destination)
    out: list[LatLon] = []
    for fraction in fractions:
        mid = destination_point(origin, bearing, crow * fraction)
        out.extend(destination_point(mid, bearing + 90 * side, offset) for side in (1, -1))
    return out


def via_points(fastest: Route, fractions: tuple[float, ...], crow_m: float) -> list[LatLon]:
    """Points either side of the fastest route itself, for a second round of detours."""
    offset = min(150_000, max(20_000, 0.15 * crow_m))
    out: list[LatLon] = []
    for fraction in fractions:
        d = fastest.distance_m * fraction
        a = point_at_distance(fastest.points, fastest.cum_distance_m, max(0.0, d - 2_000))
        b = point_at_distance(fastest.points, fastest.cum_distance_m, min(fastest.distance_m, d + 2_000))
        mid = point_at_distance(fastest.points, fastest.cum_distance_m, d)
        out.extend(destination_point(mid, bearing_deg(a, b) + 90 * side, offset) for side in (1, -1))
    return out


def _add_detours(routes: list[Route], candidates: list[Route | None]) -> None:
    fastest = routes[0]
    for candidate in candidates:
        if len(routes) >= WANTED_ROUTES:
            return
        if candidate is None or candidate.drive_s > fastest.drive_s * MAX_SLOWDOWN:
            continue
        if _overlap_with(candidate, routes) < SAME_ROUTE_OVERLAP:
            candidate.notes.append("Detour alternative: the routing API returned fewer than 3 routes.")
            routes.append(candidate)


def three_routes(provider: RoutingProvider, request: RouteRequest) -> list[Route]:
    """The provider's routes, topped up with detours to reach three distinct ones.

    The main request and the first two detours run in parallel, so a provider
    that returns no alternatives costs one round trip, not two. Only if those
    detours are unusable does a second round go out.
    """
    first_round = detour_points(request.origin, request.destination)
    with ThreadPoolExecutor(max_workers=1 + len(first_round)) as pool:
        main = pool.submit(provider.routes, request, alternatives=WANTED_ROUTES - 1)
        detours = [pool.submit(provider.route_via, request, via) for via in first_round]
        routes = distinct_routes(main.result(), WANTED_ROUTES)
        if not routes:
            return routes
        if len(routes) < WANTED_ROUTES:
            _add_detours(routes, [f.result() for f in detours])

    if len(routes) < WANTED_ROUTES:
        crow = haversine_m(request.origin, request.destination)
        second_round = via_points(routes[0], (0.35, 0.65), crow)
        with ThreadPoolExecutor(max_workers=len(second_round)) as pool:
            _add_detours(routes, list(pool.map(lambda via: provider.route_via(request, via), second_round)))
    return routes
