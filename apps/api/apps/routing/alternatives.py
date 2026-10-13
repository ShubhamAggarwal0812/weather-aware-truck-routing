"""Get three genuinely different routes.

Providers often return fewer alternatives than asked for (TomTom returns none
for most future departures). Extra routes are forced through points offset to
either side of the trip and kept only if they are distinct and not absurdly slow.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor

from common.geo import (
    LatLon,
    bearing_deg,
    destination_point,
    haversine_m,
    point_at_distance,
    sample_distances,
)

from .providers.base import Route, RouteRequest, RoutingProvider

log = logging.getLogger(__name__)

WANTED_ROUTES = 3
MAX_SLOWDOWN = 1.6  # a detour may take at most 60% longer than the fastest route
SAME_ROUTE_OVERLAP = 0.85  # sharing more than this much distance counts as the same route
NEAR_METERS = 1_000
CELL_DEGREES = 0.02
# Both carriageways of a divided road lie within SPUR_NEAR_METERS of each other, and an
# ordinary turn at a via point retraces far less than MAX_SPUR_METERS.
MAX_SPUR_METERS = 2_000
SPUR_NEAR_METERS = 150
SPUR_WINDOW_METERS = 100_000
SPUR_CELL_DEGREES = 0.005
TURNAROUND_SEARCH_STEP_METERS = 1_000
RETURN_SAMPLE_STEP_METERS = 100
OUTWARD_SAMPLE_STEP_METERS = 200


class _RouteIndex:
    # Only the 3 x 3 cells around a point are searched, so a cell must be at least near_meters across.
    def __init__(self, cell_degrees: float = CELL_DEGREES, near_meters: float = NEAR_METERS) -> None:
        self.cell_degrees = cell_degrees
        self.near_meters = near_meters
        self.cells: dict[tuple[int, int], list[LatLon]] = defaultdict(list)

    def _cell(self, point: LatLon) -> tuple[int, int]:
        return (math.floor(point[0] / self.cell_degrees), math.floor(point[1] / self.cell_degrees))

    def add(
        self, route: Route, step_meters: float = 500, start_meters: float = 0.0, end_meters: float | None = None
    ) -> None:
        last_meters = route.distance_m if end_meters is None else end_meters
        for distance in sample_distances(start_meters, last_meters, step_meters):
            point = point_at_distance(route.points, route.cum_distance_m, distance)
            self.cells[self._cell(point)].append(point)

    def near(self, point: LatLon) -> bool:
        row, column = self._cell(point)
        return any(
            haversine_m(point, indexed) <= self.near_meters
            for row_offset in (-1, 0, 1)
            for column_offset in (-1, 0, 1)
            for indexed in self.cells.get((row + row_offset, column + column_offset), ())
        )


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


def spur_length_meters(route: Route) -> float:
    if route.via is None:
        return 0.0
    via = route.via

    def position_at(distance: float) -> LatLon:
        return point_at_distance(route.points, route.cum_distance_m, distance)

    turnaround = min(
        sample_distances(0.0, route.distance_m, TURNAROUND_SEARCH_STEP_METERS),
        key=lambda distance: haversine_m(position_at(distance), via),
    )
    return_leg = _RouteIndex(cell_degrees=SPUR_CELL_DEGREES, near_meters=SPUR_NEAR_METERS)
    return_leg.add(
        route,
        step_meters=RETURN_SAMPLE_STEP_METERS,
        start_meters=turnaround,
        end_meters=min(route.distance_m, turnaround + SPUR_WINDOW_METERS),
    )
    outward_start = max(0.0, turnaround - SPUR_WINDOW_METERS)
    outward = list(sample_distances(outward_start, turnaround, OUTWARD_SAMPLE_STEP_METERS))
    # Each outward sample stands for the stretch after it, so the last one, the turnaround itself, isn't outward road.
    outward_road = outward[:-1]
    return OUTWARD_SAMPLE_STEP_METERS * sum(return_leg.near(position_at(distance)) for distance in outward_road)


def _add_detours(routes: list[Route], candidates: list[Route | None]) -> None:
    fastest = routes[0]
    for candidate in candidates:
        if len(routes) >= WANTED_ROUTES:
            return
        if candidate is None or candidate.drive_s > fastest.drive_s * MAX_SLOWDOWN:
            continue
        # A via point on a dead-end road makes the route drive down it and back, which isn't an alternative.
        if spur_length_meters(candidate) > MAX_SPUR_METERS:
            log.info("detour via %s doubles back on itself, skipping", candidate.via)
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
    pool = ThreadPoolExecutor(max_workers=1 + len(first_round))
    try:
        main = pool.submit(provider.routes, request, alternatives=WANTED_ROUTES - 1)
        detours = [pool.submit(provider.route_via, request, via) for via in first_round]
        routes = distinct_routes(main.result(), WANTED_ROUTES)
        if not routes:
            return routes
        if len(routes) < WANTED_ROUTES:
            _add_detours(routes, [_detour_or_none(future) for future in detours])
    finally:
        # Neither a failed main request nor one that already has three routes should wait for the detours.
        pool.shutdown(wait=False)

    if len(routes) < WANTED_ROUTES:
        crow = haversine_m(request.origin, request.destination)
        second_round = via_points(routes[0], (0.35, 0.65), crow)
        with ThreadPoolExecutor(max_workers=len(second_round)) as pool:
            futures = [pool.submit(provider.route_via, request, via) for via in second_round]
            _add_detours(routes, [_detour_or_none(future) for future in futures])
    return routes


def _detour_or_none(future: Future[Route | None]) -> Route | None:
    try:
        return future.result()
    except Exception:
        # Detours are optional, so any failure, not only a RoutingError, must leave the plan intact.
        log.warning("detour request failed", exc_info=True)
        return None
