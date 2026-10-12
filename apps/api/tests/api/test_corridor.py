from datetime import UTC

from rest_framework.test import APIClient

from tests.fakes import FakeProvider, FakeWeather, storm

from .conftest import install

client = APIClient()


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
