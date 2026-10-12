"""Checkpoint placement along a route and the stretch of road each one stands for.

Checkpoints sit at mile 0, every ``interval`` miles after that, and at the
destination. Each checkpoint represents the road from the midpoint with its
previous checkpoint to the midpoint with its next one, so the stretches tile
the route exactly and "miles at Severe" adds up to the route length.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.geo import METERS_PER_MILE


@dataclass(frozen=True)
class Placement:
    index: int
    distance_m: float
    covers_from_m: float
    covers_to_m: float

    @property
    def covered_m(self) -> float:
        return self.covers_to_m - self.covers_from_m


def place_checkpoints(route_length_m: float, interval_miles: float) -> list[Placement]:
    if route_length_m <= 0:
        return [Placement(0, 0.0, 0.0, 0.0)]
    step = interval_miles * METERS_PER_MILE
    distances = [i * step for i in range(int(route_length_m // step) + 1)]
    if route_length_m - distances[-1] > 1.0:
        distances.append(route_length_m)

    placements = []
    for i, d in enumerate(distances):
        start = 0.0 if i == 0 else (distances[i - 1] + d) / 2
        end = route_length_m if i == len(distances) - 1 else (d + distances[i + 1]) / 2
        placements.append(Placement(i, d, start, end))
    return placements
