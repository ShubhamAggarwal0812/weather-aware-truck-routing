"""Hourly weather and risk on a grid around the routes, for the heatmap."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.trips.domain.corridor import corridor_grid
from apps.trips.domain.risk import assess
from apps.weather.exceptions import WeatherError
from apps.weather.forecast import HOUR, ForecastSource, floor_hour, forecast_limit
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
    if start + hours * HOUR > forecast_limit():
        raise WeatherError("The heatmap window runs past the 16-day forecast. Choose an earlier departure.")
    # One extra hour so the last hour's precipitation total is available.
    series = weather.hourly(grid.centers, start, start + hours * HOUR) if grid.cells else []
    wind, rain, snow, risk = [], [], [], []
    for h in range(hours):
        samples = [s.hour(h) for s in series]
        wind.append([round(s.wind_mph, 1) for s in samples])
        rain.append([round(s.rain_in_hr, 3) for s in samples])
        snow.append([round(s.snow_in_hr, 3) for s in samples])
        risk.append([int(assess(conditions(s), load_weight_lb).level) for s in samples])
    return {
        "step_deg": grid.step_deg,
        "rows": [r for r, _ in grid.cells],
        "cols": [c for _, c in grid.cells],
        "times": [iso(start + h * HOUR) for h in range(hours)],
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
        "risk": risk,
    }
