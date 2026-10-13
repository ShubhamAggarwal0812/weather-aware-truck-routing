from datetime import datetime, timedelta

import pytest
import respx
from django.core.cache import caches
from rest_framework.test import APIClient

from apps.routing.exceptions import RoutingError
from apps.trips.api import views
from apps.weather.budget import WeatherBudget
from tests.fakes import FakeProvider, FakeWeather, storm, straight_route

from .conftest import install

ORIGIN, DEST = (40.0, -105.0), (40.0, -95.0)


def body(when, **overrides):
    data = {
        "origin": {"lat": ORIGIN[0], "lon": ORIGIN[1], "label": "Origin"},
        "destination": {"lat": DEST[0], "lon": DEST[1], "label": "Destination"},
        "departure": when.isoformat(),
        "load_weight_lb": 35_000,
        "interval_miles": 25,
    }
    data.update(overrides)
    return data


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def three_roads():
    """A: straight and fastest. B: north detour. C: south detour."""
    return [
        straight_route(ORIGIN, DEST, summary="via middle"),
        straight_route(ORIGIN, DEST, via=(41.6, -100.0), summary="via north"),
        straight_route(ORIGIN, DEST, via=(38.4, -100.0), summary="via south"),
    ]


PLAN_URL = "/api/v1/trips/plan"


def test_should_recommend_the_route_that_avoids_no_travel_wind(client, monkeypatch, departure, three_roads):
    install(monkeypatch, FakeProvider(three_roads), FakeWeather(storm))
    res = client.post(PLAN_URL, body(departure, load_weight_lb=35_000), format="json")
    assert res.status_code == 200, res.data
    data = res.json()
    routes = {r["id"]: r for r in data["routes"]}
    # 45-54 mph with > 30,000 lb is No Travel; route A and C cross the storm.
    assert routes["A"]["risk"]["miles_by_level"]["no_travel"] > 0
    assert routes["C"]["risk"]["miles_by_level"]["no_travel"] > 0
    assert routes["B"]["risk"]["miles_by_level"]["no_travel"] == 0
    assert data["recommendation"]["route_id"] == "B"
    assert data["recommendation"]["safe"] is True
    assert routes["B"]["recommended"]
    assert routes["B"]["rank"] == 1
    assert any("No Travel" in reason for reason in data["recommendation"]["reasons"])
    storm_cp = next(cp for cp in routes["A"]["checkpoints"] if cp["level"] == "no_travel")
    wind = next(f for f in storm_cp["factors"] if f["condition"] == "wind")
    assert "30,000" in wind["load_rule"]
    assert storm_cp["drivers"] == ["wind"]


def test_the_same_wind_is_only_severe_for_a_light_load(client, monkeypatch, departure, three_roads):
    install(monkeypatch, FakeProvider(three_roads), FakeWeather(storm))
    data = client.post(PLAN_URL, body(departure, load_weight_lb=20_000), format="json").json()
    a = next(r for r in data["routes"] if r["id"] == "A")
    assert a["risk"]["miles_by_level"]["no_travel"] == 0
    assert a["risk"]["miles_by_level"]["severe"] > 0


def test_weather_is_sampled_at_each_checkpoints_eta(client, monkeypatch, departure):
    # 60 mph from -105 to -95 along 40N reaches -100 after ~4.4 h of driving.
    window = (departure + timedelta(hours=3.5), departure + timedelta(hours=5.5))

    def passing_storm(lat, lon, t):
        active = window[0] <= t <= window[1]
        return (60.0, 0.0, 0.0) if active and -100.3 <= lon <= -99.7 else (5.0, 0.0, 0.0)

    install(monkeypatch, FakeProvider([straight_route(ORIGIN, DEST)]), FakeWeather(passing_storm))
    data = client.post(PLAN_URL, body(departure, interval_miles=10), format="json").json()
    hits = [cp for cp in data["routes"][0]["checkpoints"] if cp["level"] == "no_travel"]
    assert hits
    for cp in hits:
        eta = datetime.fromisoformat(cp["eta"])
        assert window[0] - timedelta(hours=1) <= eta <= window[1] + timedelta(hours=1)

    later = departure + timedelta(hours=8)
    data = client.post(PLAN_URL, body(later, interval_miles=10), format="json").json()
    assert data["routes"][0]["risk"]["max_level"] == "low"


def test_should_add_checkpoint_miles_up_to_the_route(client, monkeypatch, departure, three_roads):
    install(monkeypatch, FakeProvider(three_roads), FakeWeather())
    data = client.post(PLAN_URL, body(departure, interval_miles=10), format="json").json()
    for r in data["routes"]:
        assert sum(r["risk"]["miles_by_level"].values()) == pytest.approx(r["distance_mi"], abs=0.3)
        miles = [cp["mile"] for cp in r["checkpoints"]]
        assert miles[0] == 0
        assert miles[1] == 10
        assert miles[-1] == r["distance_mi"]


def test_rest_breaks_push_back_long_trip_etas(client, monkeypatch, departure):
    far = (40.0, -80.0)  # ~1,300 mi at 60 mph: about 22 h of driving
    route = straight_route(ORIGIN, far)
    install(monkeypatch, FakeProvider([route]), FakeWeather())
    req = body(departure, destination={"lat": far[0], "lon": far[1]})
    with_breaks = client.post(PLAN_URL, req, format="json").json()["routes"][0]
    without = client.post(PLAN_URL, {**req, "rest_breaks": False}, format="json").json()["routes"][0]
    assert without["travel_time_s"] == without["drive_time_s"]
    assert with_breaks["travel_time_s"] == pytest.approx(with_breaks["drive_time_s"] + 21 * 3600, abs=2)
    assert [s["kind"] for s in with_breaks["stops"]] == ["break", "rest", "break", "rest"]


def test_should_follow_the_trip_with_the_truck_positions(client, monkeypatch, departure):
    install(monkeypatch, FakeProvider([straight_route(ORIGIN, DEST)]), FakeWeather())
    data = client.post(PLAN_URL, body(departure), format="json").json()
    positions = data["routes"][0]["positions"]
    assert len(positions) == 48 * 4 + 1
    codes = [p[2] for p in positions]
    assert codes[0] == 0  # the window starts at the top of the departure hour, before departure
    assert 1 in codes
    assert codes[-1] == 4
    assert positions[-1][:2] == pytest.approx(list(DEST), abs=1e-3)


def test_sends_gross_truck_weight_to_the_router(client, monkeypatch, departure):
    provider = FakeProvider([straight_route(ORIGIN, DEST)])
    install(monkeypatch, provider, FakeWeather())
    client.post(PLAN_URL, body(departure, load_weight_lb=42_000), format="json")
    assert provider.requests[0].gross_weight_lb == 77_000


def test_identical_requests_are_served_from_cache(client, monkeypatch, departure):
    provider = FakeProvider([straight_route(ORIGIN, DEST)])
    install(monkeypatch, provider, FakeWeather())
    client.post(PLAN_URL, body(departure), format="json")
    client.post(PLAN_URL, body(departure), format="json")
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"interval_miles": 15}, "interval_miles"),
        ({"load_weight_lb": -1}, "load_weight_lb"),
        ({"load_weight_lb": 90_000}, "load_weight_lb"),
        ({"departure": "2020-01-01T00:00:00Z"}, "departure"),
        ({"destination": {"lat": 40.0, "lon": -105.0}}, "destination"),
        ({"origin": {"lat": 120, "lon": 0}}, "origin"),
    ],
)
def test_validation_errors(client, monkeypatch, departure, overrides, field):
    install(monkeypatch, FakeProvider([]), FakeWeather())
    res = client.post(PLAN_URL, body(departure, **overrides), format="json")
    assert res.status_code == 400
    assert field in res.json()["fields"]


def test_departure_too_far_ahead(client, departure):
    res = client.post(PLAN_URL, body(departure + timedelta(days=8)), format="json")
    assert res.status_code == 400
    assert "7 days" in str(res.json()["fields"]["departure"])


def test_routing_errors_reach_the_user(client, monkeypatch, departure):
    class Failing(FakeProvider):
        def routes(self, request, *, alternatives):
            raise RoutingError("No truck route was found between these places.", status=422)

    install(monkeypatch, Failing([]), FakeWeather())
    res = client.post(PLAN_URL, body(departure), format="json")
    assert res.status_code == 422
    assert res.json() == {"error": "No truck route was found between these places."}


@respx.mock
def test_should_refuse_a_plan_past_the_client_weather_allowance_without_fetching(
    client, monkeypatch, settings, departure, three_roads
):
    settings.WEATHER_BUDGET = "1000/day"
    caches["limits"].clear()
    WeatherBudget("127.0.0.1").spend(999)
    monkeypatch.setattr(views, "get_routing_provider", lambda: FakeProvider(three_roads))
    open_meteo = respx.post("https://api.open-meteo.com/v1/forecast")
    response = client.post(PLAN_URL, body(departure), format="json")
    assert response.status_code == 429
    assert "weather data" in response.json()["error"]
    assert open_meteo.call_count == 0


def test_should_show_gusts_and_temperature_the_forecast_left_out_as_null(client, monkeypatch, departure, three_roads):
    install(monkeypatch, FakeProvider(three_roads), FakeWeather(storm, gusts_and_temperature_known=False))
    response = client.post(PLAN_URL, body(departure), format="json")
    assert response.status_code == 200, response.data
    conditions = response.json()["routes"][0]["checkpoints"][0]["conditions"]
    assert (conditions["gust_mph"], conditions["temp_f"]) == (None, None)
    assert conditions["wind_mph"] > 0
