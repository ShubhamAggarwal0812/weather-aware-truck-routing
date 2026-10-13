"""Small geodesy helpers. Points are (lat, lon) tuples in degrees."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Iterator, Sequence
from itertools import pairwise

LatLon = tuple[float, float]

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances(points: Sequence[LatLon]) -> list[float]:
    """Distance from the first point to each point along the polyline, in meters."""
    cum = [0.0]
    for prev, cur in pairwise(points):
        cum.append(cum[-1] + haversine_m(prev, cur))
    return cum


def interpolate(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    """Piecewise-linear y(x) for increasing xs, clamped at both ends."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x) - 1
    span = xs[i + 1] - xs[i]
    if span <= 0:
        return ys[i + 1]
    return ys[i] + (ys[i + 1] - ys[i]) * (x - xs[i]) / span


def sample_distances(start_meters: float, end_meters: float, step_meters: float) -> Iterator[float]:
    distance = start_meters
    while distance < end_meters:
        yield distance
        distance += step_meters
    yield end_meters


def point_at_distance(points: Sequence[LatLon], cum: Sequence[float], distance_m: float) -> LatLon:
    """Position along the polyline at the given distance from its start."""
    if distance_m <= 0:
        return points[0]
    if distance_m >= cum[-1]:
        return points[-1]
    i = bisect_right(cum, distance_m) - 1
    span = cum[i + 1] - cum[i]
    t = 0.0 if span <= 0 else (distance_m - cum[i]) / span
    (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


def slice_polyline(points: Sequence[LatLon], cum: Sequence[float], start_m: float, end_m: float) -> list[LatLon]:
    """Sub-polyline between two distances, with interpolated end points."""
    start_m = max(0.0, start_m)
    end_m = min(cum[-1], end_m)
    out = [point_at_distance(points, cum, start_m)]
    i = bisect_right(cum, start_m)
    while i < len(points) and cum[i] < end_m:
        out.append(points[i])
        i += 1
    out.append(point_at_distance(points, cum, end_m))
    return out


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(origin: LatLon, bearing: float, distance_m: float) -> LatLon:
    lat1, lon1 = map(math.radians, origin)
    brg = math.radians(bearing)
    d = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return (math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def simplify(points: Sequence[LatLon], tolerance_m: float) -> list[LatLon]:
    """Douglas-Peucker simplification on a local equirectangular projection."""
    if len(points) < 3:
        return list(points)
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    kx = EARTH_RADIUS_M * math.cos(lat0) * math.pi / 180
    ky = EARTH_RADIUS_M * math.pi / 180
    xy = [(lon * kx, lat * ky) for lat, lon in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    tol2 = tolerance_m * tolerance_m
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = xy[first], xy[last]
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx * dx + dy * dy
        worst, worst_d2 = -1, tol2
        for i in range(first + 1, last):
            px, py = xy[i]
            if seg2 == 0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg2))
                d2 = (px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2
            if d2 > worst_d2:
                worst, worst_d2 = i, d2
        if worst != -1:
            keep[worst] = True
            stack.append((first, worst))
            stack.append((worst, last))
    return [p for p, k in zip(points, keep) if k]
