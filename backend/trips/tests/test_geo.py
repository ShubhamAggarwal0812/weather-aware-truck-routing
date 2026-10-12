import pytest

from trips.domain.geo import (
    cumulative_distances,
    destination_point,
    haversine_m,
    point_at_distance,
    simplify,
    slice_polyline,
)


def test_haversine_known_distance():
    # Denver to Chicago is about 920 mi as the crow flies.
    assert haversine_m((39.7392, -104.9903), (41.8781, -87.6298)) / 1609.344 == pytest.approx(920, abs=5)


def test_point_at_distance_and_slice():
    pts = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cum = cumulative_distances(pts)
    mid = point_at_distance(pts, cum, cum[-1] / 2)
    assert mid == pytest.approx((0.0, 1.0))
    part = slice_polyline(pts, cum, cum[1] / 2, cum[1] * 1.5)
    assert part[0] == pytest.approx((0.0, 0.5))
    assert part[1] == (0.0, 1.0)
    assert part[-1] == pytest.approx((0.0, 1.5))


def test_simplify_drops_collinear_points_and_keeps_corners():
    pts = [(0.0, i * 0.01) for i in range(50)] + [(i * 0.01, 0.49) for i in range(1, 50)]
    out = simplify(pts, 10)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert (0.0, 0.49) in out
    assert len(out) == 3


def test_destination_point_round_trip():
    p = destination_point((40.0, -100.0), 90, 100_000)
    assert haversine_m((40.0, -100.0), p) == pytest.approx(100_000, rel=1e-6)
