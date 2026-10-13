from datetime import UTC

import respx
from django.core.cache import caches
from rest_framework.test import APIClient

from apps.weather.budget import WeatherBudget
from tests.fakes import FakeProvider, FakeWeather, back_and_forth_line, storm

from .conftest import install

client = APIClient()
TEST_CLIENT_ADDRESS = "127.0.0.1"


def test_corridor_grid_has_risk_for_every_hour(monkeypatch, departure):
    weather = FakeWeather(storm)
    install(monkeypatch, FakeProvider([]), weather)
    lines = [[[40.0, -105.0], [40.0, -95.0]]]
    res = client.post(
        "/api/v1/trips/corridor-forecast",
        {"lines": lines, "departure": departure.isoformat(), "load_weight_lb": 35_000},
        format="json",
    )
    assert res.status_code == 200, res.data
    data = res.json()
    n = len(data["rows"])
    assert n == len(data["cols"]) > 0
    assert len(data["times"]) == len(data["risk"]) == len(data["wind_mph"]) == 49
    assert all(len(hour) == n for hour in data["risk"])
    assert max(max(h) for h in data["risk"]) == 4  # the storm band is No Travel for 35,000 lb
    assert data["times"][0] == departure.replace(minute=0).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _post_corridor(lines, departure):
    return client.post(
        "/api/v1/trips/corridor-forecast",
        {"lines": lines, "departure": departure.isoformat(), "load_weight_lb": 35_000},
        format="json",
    )


def test_should_accept_a_coast_to_coast_line(monkeypatch, departure):
    install(monkeypatch, FakeProvider([]), FakeWeather(storm))
    coast_to_coast = [[25.76, -80.19], [39.74, -104.99], [47.61, -122.33]]
    response = _post_corridor([coast_to_coast], departure)
    assert response.status_code == 200, response.data


def test_should_reject_a_line_longer_than_any_route_without_fetching(monkeypatch, departure):
    weather = FakeWeather(storm)
    install(monkeypatch, FakeProvider([]), weather)
    there_and_back_half_way_round_the_world = [[0.0, 0.0], [0.0, 179.0], [0.0, 0.0]]
    response = _post_corridor([there_and_back_half_way_round_the_world], departure)
    assert response.status_code == 400
    assert "lines" in response.json()["fields"]
    assert weather.calls == []


def test_should_refuse_a_corridor_past_the_cell_cap_without_fetching(monkeypatch, departure):
    weather = FakeWeather(storm)
    install(monkeypatch, FakeProvider([]), weather)
    lines = [back_and_forth_line(26, 34), back_and_forth_line(34, 42), back_and_forth_line(42, 49)]
    response = _post_corridor(lines, departure)
    assert response.status_code == 422
    assert "too much ground" in response.json()["error"]
    assert weather.calls == []


@respx.mock
def test_should_refuse_a_heatmap_past_the_client_weather_allowance_without_fetching(settings, departure):
    settings.WEATHER_BUDGET = "1000/day"
    caches["limits"].clear()
    WeatherBudget(TEST_CLIENT_ADDRESS).spend(990)
    open_meteo = respx.post("https://api.open-meteo.com/v1/forecast")
    response = _post_corridor([[[40.0, -105.0], [40.0, -95.0]]], departure)
    assert response.status_code == 429
    assert "weather data" in response.json()["error"]
    assert open_meteo.call_count == 0
