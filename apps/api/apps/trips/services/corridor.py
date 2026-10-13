"""Hourly weather and risk on a grid around the routes, for the heatmap."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.trips.domain.corridor import corridor_grid
from apps.trips.domain.risk import assess
from apps.weather.forecast import HOUR, ForecastSource, floor_hour
from common.geo import LatLon

from .planning import conditions
from .presenters import HEATMAP_HOURS, iso


def corridor_forecast(
    lines: list[list[LatLon]], departure: datetime, load_weight_lb: int, weather: ForecastSource
) -> dict[str, Any]:
    """Hours 0..48 from the departure hour, for every grid cell within the corridor."""
    grid = corridor_grid(lines)
    start = floor_hour(departure)
    hours = HEATMAP_HOURS + 1
    series = weather.hourly(grid.centers, start, start + HEATMAP_HOURS * HOUR) if grid.cells else []
    wind, rain, snow, risk = [], [], [], []
    for hour in range(hours):
        samples = [cell_series.hour(hour) for cell_series in series]
        wind.append([round(sample.wind_mph, 1) for sample in samples])
        rain.append([round(sample.rain_in_hr, 3) for sample in samples])
        snow.append([round(sample.snow_in_hr, 3) for sample in samples])
        risk.append([int(assess(conditions(sample), load_weight_lb).level) for sample in samples])
    return {
        "step_deg": grid.step_deg,
        "rows": [row for row, _ in grid.cells],
        "cols": [column for _, column in grid.cells],
        "times": [iso(start + hour * HOUR) for hour in range(hours)],
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
        "risk": risk,
    }
