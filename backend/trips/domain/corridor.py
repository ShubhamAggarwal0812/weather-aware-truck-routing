"""The grid of forecast points that backs the weather heatmap.

Cells sit on a global lat/lon grid (cell (r, c) is centred on r*step, c*step),
so the same cell always has the same coordinates and its forecast can be cached
across trips. Only cells within ``buffer`` of a route are kept. The step grows
until the corridor fits ``max_cells``, which bounds the cost of a long trip.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .geo import METERS_PER_MILE, LatLon, cumulative_distances, haversine_m, point_at_distance

STEPS_DEG = (0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
DEFAULT_BUFFER_M = 30 * METERS_PER_MILE
DEFAULT_MAX_CELLS = 600
METERS_PER_DEG_LAT = 111_195.0


@dataclass(frozen=True)
class CorridorGrid:
    step_deg: float
    cells: tuple[tuple[int, int], ...]  # (row, col) on the global grid, sorted

    def center(self, cell: tuple[int, int]) -> LatLon:
        r, c = cell
        return (round(r * self.step_deg, 4), round(c * self.step_deg, 4))

    @property
    def centers(self) -> list[LatLon]:
        return [self.center(c) for c in self.cells]


def _cells_for(routes: Sequence[Sequence[LatLon]], step: float, buffer_m: float) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    sample_m = step * METERS_PER_DEG_LAT / 2
    # A cell is kept when its centre is within buffer + half a diagonal of the route,
    # so the corridor edge is a full ring of cells rather than a ragged one.
    reach_m = buffer_m + step * METERS_PER_DEG_LAT * 0.71
    for points in routes:
        if len(points) < 2:
            continue
        cum = cumulative_distances(points)
        d = 0.0
        while True:
            lat, lon = point_at_distance(points, cum, d)
            r0, c0 = round(lat / step), round(lon / step)
            dr = math.ceil(reach_m / (step * METERS_PER_DEG_LAT))
            dc = math.ceil(reach_m / (step * METERS_PER_DEG_LAT * max(0.2, math.cos(math.radians(lat)))))
            for r in range(r0 - dr, r0 + dr + 1):
                for c in range(c0 - dc, c0 + dc + 1):
                    if (r, c) not in cells and haversine_m((lat, lon), (r * step, c * step)) <= reach_m:
                        cells.add((r, c))
            if d >= cum[-1]:
                break
            d = min(cum[-1], d + sample_m)
    return cells


def _estimated_cells(total_length_m: float, step: float, buffer_m: float, mean_lat: float) -> float:
    cell_m2 = (step * METERS_PER_DEG_LAT) ** 2 * max(0.2, math.cos(math.radians(mean_lat)))
    return (total_length_m * 2 * buffer_m + math.pi * buffer_m**2) / cell_m2


def corridor_grid(
    routes: Sequence[Sequence[LatLon]],
    *,
    buffer_m: float = DEFAULT_BUFFER_M,
    max_cells: int = DEFAULT_MAX_CELLS,
) -> CorridorGrid:
    routes = [r for r in routes if len(r) >= 2]
    if not routes:
        return CorridorGrid(STEPS_DEG[0], ())
    total_m = sum(cumulative_distances(r)[-1] for r in routes)
    mean_lat = sum(lat for r in routes for lat, _ in r) / sum(len(r) for r in routes)
    # Alternatives share road, so the summed length overestimates the corridor. Skip
    # steps that would be over budget even if the routes overlapped by half.
    steps = [s for s in STEPS_DEG if _estimated_cells(total_m, s, buffer_m, mean_lat) * 0.5 <= max_cells]
    cells: set[tuple[int, int]] = set()
    for step in steps or STEPS_DEG[-1:]:
        cells = _cells_for(routes, step, buffer_m)
        if len(cells) <= max_cells:
            return CorridorGrid(step, tuple(sorted(cells)))
    # Continental-scale trips: keep the coarsest grid even if it's over budget.
    return CorridorGrid(STEPS_DEG[-1], tuple(sorted(cells)))
