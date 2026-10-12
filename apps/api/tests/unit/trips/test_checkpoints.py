from itertools import pairwise

import pytest

from apps.trips.domain.checkpoints import place_checkpoints
from common.geo import METERS_PER_MILE

MI = METERS_PER_MILE


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_every_interval_plus_destination(interval):
    cps = place_checkpoints(103 * MI, interval)
    miles = [round(c.distance_m / MI, 3) for c in cps]
    assert miles[0] == 0
    assert miles[-1] == 103
    assert all(b - a == pytest.approx(interval) for a, b in pairwise(miles[:-1]))


def test_coverage_tiles_the_route():
    cps = place_checkpoints(103 * MI, 25)
    assert cps[0].covers_from_m == 0
    assert cps[-1].covers_to_m == pytest.approx(103 * MI)
    for a, b in pairwise(cps):
        assert a.covers_to_m == pytest.approx(b.covers_from_m)
    assert sum(c.covered_m for c in cps) == pytest.approx(103 * MI)


def test_midpoint_coverage():
    cps = place_checkpoints(60 * MI, 25)  # 0, 25, 50, 60
    assert [round(c.covers_from_m / MI, 1) for c in cps] == [0, 12.5, 37.5, 55]
    assert [round(c.covers_to_m / MI, 1) for c in cps] == [12.5, 37.5, 55, 60]


def test_exact_multiple_has_no_duplicate_destination():
    cps = place_checkpoints(50 * MI, 25)
    assert [round(c.distance_m / MI) for c in cps] == [0, 25, 50]


def test_route_shorter_than_interval():
    cps = place_checkpoints(4 * MI, 10)
    assert [round(c.distance_m / MI) for c in cps] == [0, 4]
