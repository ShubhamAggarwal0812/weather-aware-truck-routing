import pytest

from apps.trips.domain.corridor import MAX_CELLS, CorridorTooLarge, corridor_grid
from common.geo import METERS_PER_MILE, haversine_m
from tests.fakes import back_and_forth_line


def test_cells_cover_the_route_within_the_buffer():
    line = [(40.0, -100.0 + i * 0.1) for i in range(31)]  # ~160 mi east-west
    grid = corridor_grid([line], buffer_m=30 * METERS_PER_MILE, max_cells=10_000)
    assert grid.step_deg == 0.1
    for center in grid.centers:
        nearest = min(haversine_m(center, p) for p in line)
        assert nearest <= (30 + 6) * METERS_PER_MILE
    # The route itself is fully inside the corridor.
    cells = set(grid.cells)
    for lat, lon in line:
        assert (round(lat / grid.step_deg), round(lon / grid.step_deg)) in cells


def test_step_grows_to_fit_the_budget():
    line = [(35.0 + i * 0.05, -120.0 + i * 0.25) for i in range(100)]  # ~1,400 mi
    grid = corridor_grid([line], max_cells=600)
    assert len(grid.cells) <= 600
    assert grid.step_deg > 0.1


def test_cells_are_on_a_global_grid():
    grid = corridor_grid([[(40.03, -100.02), (40.5, -99.5)]])
    for lat, lon in grid.centers:
        assert abs(lat / grid.step_deg - round(lat / grid.step_deg)) < 1e-6
        assert abs(lon / grid.step_deg - round(lon / grid.step_deg)) < 1e-6


def test_should_let_the_coarsest_grid_exceed_the_budget_for_a_continental_trip():
    coast_to_coast = [
        [(start_latitude + step * 0.2, -122.0 + step * 0.5) for step in range(101)]
        for start_latitude in (26.0, 32.0, 38.0)
    ]
    grid = corridor_grid(coast_to_coast, max_cells=200)
    assert grid.step_deg == 1.0
    assert 200 < len(grid.cells) <= MAX_CELLS


def test_should_refuse_a_corridor_that_exceeds_the_hard_cap_even_on_the_coarsest_grid():
    blanket_of_lines = [back_and_forth_line(26, 34), back_and_forth_line(34, 42), back_and_forth_line(42, 49)]
    with pytest.raises(CorridorTooLarge):
        corridor_grid(blanket_of_lines)
