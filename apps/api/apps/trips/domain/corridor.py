"""The grid of forecast points that backs the weather heatmap.

Cells sit on a global lat/lon grid (cell (r, c) is centred on r*step, c*step),
so the same cell always has the same coordinates and its forecast can be cached
across trips. Only cells within ``buffer`` of a route are kept. The step grows
until the corridor fits ``max_cells``, which bounds the cost of a long trip.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from common.exceptions import ServiceError
from common.geo import METERS_PER_MILE, LatLon, cumulative_distances, haversine_m, point_at_distance

STEPS_DEG = (0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
DEFAULT_BUFFER_M = 30 * METERS_PER_MILE
# Each cell is one Open-Meteo call; the free tier allows 600 a minute per IP.
DEFAULT_MAX_CELLS = 300
# The lines come from the client and every cell costs an Open-Meteo call, so even the
# coarsest grid stops here; three real coast-to-coast routes come to 250-300 cells.
MAX_CELLS = 600
METERS_PER_DEG_LAT = 111_195.0


class CorridorTooLarge(ServiceError):
    default_status = 422

    def __init__(self) -> None:
        super().__init__("These routes cover too much ground for the weather heatmap.")


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


def _cells_for(
    routes: Sequence[Sequence[LatLon]], step: float, buffer_m: float, limit: int
) -> set[tuple[int, int]] | None:
    cells: set[tuple[int, int]] = set()
    sample_m = step * METERS_PER_DEG_LAT / 2
    # A cell is kept when its centre is within buffer + half a diagonal of the route,
    # so the corridor edge is a full ring of cells rather than a ragged one.
    reach_m = buffer_m + step * METERS_PER_DEG_LAT * 0.71
    for points in routes:
        if len(points) < 2:
            continue
        cum = cumulative_distances(points)
        for distance in _sample_distances(cum[-1], sample_m):
            _add_cells_near(cells, point_at_distance(points, cum, distance), step, reach_m)
            if len(cells) > limit:
                return None
    return cells


def _sample_distances(length_meters: float, step_meters: float) -> Iterator[float]:
    distance = 0.0
    while distance < length_meters:
        yield distance
        distance += step_meters
    yield length_meters


def _add_cells_near(cells: set[tuple[int, int]], point: LatLon, step: float, reach_meters: float) -> None:
    latitude = point[0]
    row_center, column_center = round(latitude / step), round(point[1] / step)
    rows = math.ceil(reach_meters / (step * METERS_PER_DEG_LAT))
    columns = math.ceil(reach_meters / (step * METERS_PER_DEG_LAT * max(0.2, math.cos(math.radians(latitude)))))
    for row in range(row_center - rows, row_center + rows + 1):
        for column in range(column_center - columns, column_center + columns + 1):
            if (row, column) not in cells and haversine_m(point, (row * step, column * step)) <= reach_meters:
                cells.add((row, column))


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
    for step in steps or STEPS_DEG[-1:]:
        # Continental trips don't fit the budget at any step, so the coarsest grid may exceed it up to the hard cap.
        limit = max(max_cells, MAX_CELLS) if step == STEPS_DEG[-1] else max_cells
        cells = _cells_for(routes, step, buffer_m, limit)
        if cells is not None:
            return CorridorGrid(step, tuple(sorted(cells)))
    raise CorridorTooLarge()
