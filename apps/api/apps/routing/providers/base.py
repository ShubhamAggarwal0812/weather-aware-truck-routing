"""Provider-neutral route model and the interface every routing provider implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from common.geo import LatLon, cumulative_distances, interpolate


@dataclass(frozen=True)
class RouteRequest:
    origin: LatLon
    destination: LatLon
    depart_at: datetime
    gross_weight_lb: int


@dataclass
class Route:
    """A drivable route with a driving-time profile along it.

    ``cum_distance_m[i]`` and ``cum_drive_s[i]`` are the distance and the
    driving time from the origin to ``points[i]``. They come from the provider's
    own per-point data, so a slow city stretch costs more time than the same
    distance of interstate.
    """

    points: list[LatLon]
    cum_distance_m: list[float]
    cum_drive_s: list[float]
    summary: str
    provider: str
    via: LatLon | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def distance_m(self) -> float:
        return self.cum_distance_m[-1]

    @property
    def drive_s(self) -> float:
        return self.cum_drive_s[-1]

    def drive_s_at(self, distance_m: float) -> float:
        return interpolate(self.cum_distance_m, self.cum_drive_s, distance_m)

    def distance_at(self, drive_s: float) -> float:
        return interpolate(self.cum_drive_s, self.cum_distance_m, drive_s)

    @classmethod
    def from_timed_points(
        cls,
        points: list[LatLon],
        timed: list[tuple[int, float]],
        *,
        length_m: float,
        duration_s: float,
        summary: str,
        provider: str,
    ) -> Route:
        """Build a route from (point index, drive seconds) samples, e.g. TomTom's ``progress``.

        Distances are measured with haversine and rescaled to the provider's
        reported length. Times between samples are interpolated by distance.
        """
        cum = cumulative_distances(points)
        scale = length_m / cum[-1] if cum[-1] > 0 else 1.0
        cum = [d * scale for d in cum]
        last = len(points) - 1
        known = {index: seconds for index, seconds in timed if 0 <= index <= last}
        known.setdefault(0, 0.0)
        known[last] = duration_s
        xs = [cum[i] for i in sorted(known)]
        ys = [known[i] for i in sorted(known)]
        drive = [interpolate(xs, ys, d) for d in cum]
        # Keep the profile monotonic; providers occasionally round a sample down.
        for i in range(1, len(drive)):
            drive[i] = max(drive[i], drive[i - 1])
        return cls(points=points, cum_distance_m=cum, cum_drive_s=drive, summary=summary, provider=provider)


class RoutingProvider(Protocol):
    name: str
    #: True when the provider routes for trucks (weight limits, truck speeds).
    truck_aware: bool

    def routes(self, request: RouteRequest, *, alternatives: int) -> list[Route]:
        """The best route plus up to ``alternatives`` others, best first."""
        ...

    def route_via(self, request: RouteRequest, via: LatLon) -> Route | None:
        """A route forced to pass near ``via``, or None if there isn't one."""
        ...
