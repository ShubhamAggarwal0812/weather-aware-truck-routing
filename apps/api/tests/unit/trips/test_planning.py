from datetime import UTC, datetime, timedelta

import pytest

from apps.routing.providers import Route
from apps.trips.services import planning
from apps.trips.services.planning import Place, TripInput, plan_trip
from apps.weather.exceptions import WeatherError
from apps.weather.forecast import HOUR, floor_hour
from common.geo import cumulative_distances
from tests.fakes import FakeProvider, FakeWeather

ORIGIN, DESTINATION = (40.0, -105.0), (40.0, -104.0)


def trip_arriving_exactly_on_the_hour():
    points = [(40.0, -105.0 + step / 100) for step in range(101)]
    route = Route.from_timed_points(
        points, [], length_m=cumulative_distances(points)[-1], duration_s=7200.0, summary="", provider="fake"
    )
    departure = floor_hour(datetime.now(UTC)) + 3 * HOUR
    trip = TripInput(Place(*ORIGIN), Place(*DESTINATION), departure, 20_000, 10, rest_breaks=False)
    return trip, FakeProvider([route]), departure + 2 * HOUR


def test_should_refuse_an_arrival_on_the_last_forecast_hour_instead_of_asking_past_it(monkeypatch):
    trip, provider, arrival = trip_arriving_exactly_on_the_hour()
    monkeypatch.setattr(planning, "forecast_limit", lambda: arrival)
    weather = FakeWeather()
    with pytest.raises(WeatherError, match="16-day"):
        plan_trip(trip, provider, weather)
    assert weather.calls == []


def test_should_end_the_forecast_window_on_the_hour_after_arrival(monkeypatch):
    trip, provider, arrival = trip_arriving_exactly_on_the_hour()
    monkeypatch.setattr(planning, "forecast_limit", lambda: arrival + HOUR)
    weather = FakeWeather()
    plan = plan_trip(trip, provider, weather)
    assert plan.routes[0].arrival == arrival
    assert [end for _, _, end in weather.calls] == [arrival + timedelta(hours=1)]
