from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from apps.weather.exceptions import WeatherError
from apps.weather.forecast import HourlySeries, OpenMeteoClient

T0 = datetime(2026, 10, 13, 12, tzinfo=UTC)
URL = "https://api.open-meteo.com/v1/forecast"


def series(**overrides):
    base = {
        "wind_mph": (10.0, 20.0, 30.0),
        "gust_mph": (15.0, 25.0, 35.0),
        "rain_in": (0.0, 0.2, 0.6),
        "snow_in": (0.0, 0.0, 1.5),
        "temp_f": (40.0, 30.0, 20.0),
    }
    base.update(overrides)
    return HourlySeries(start=T0, **base)


def test_wind_is_interpolated_to_the_exact_time():
    s = series().at(T0 + timedelta(minutes=30))
    assert s.wind_mph == pytest.approx(15.0)
    assert s.temp_f == pytest.approx(35.0)


def test_precip_uses_the_hour_ending_after_the_eta():
    # 12:30 falls in 12:00-13:00, whose total is stamped 13:00.
    assert series().at(T0 + timedelta(minutes=30)).rain_in_hr == 0.2
    # Exactly 13:00 starts the 13:00-14:00 hour.
    assert series().at(T0 + timedelta(hours=1)).rain_in_hr == 0.6
    assert series().at(T0 + timedelta(hours=1, minutes=59)).snow_in_hr == 1.5


def test_hour_index_conditions():
    s = series().hour(1)
    assert (s.wind_mph, s.rain_in_hr, s.snow_in_hr) == (20.0, 0.6, 1.5)


def _location(lat, lon, start, hours, wind=12.0):
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    n = len(times)
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": {
            "time": times,
            "wind_speed_10m": [wind] * n,
            "wind_gusts_10m": [wind + 5] * n,
            "rain": [0.1] * n,
            "showers": [0.05] * (n - 1) + [None],
            "snowfall": [0.0] * n,
            "temperature_2m": [50.0] * n,
        },
    }


@respx.mock
def test_batches_points_and_sums_rain_and_showers():
    def handler(request):
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        lats = form["latitude"].split("%2C")
        assert form["wind_speed_unit"] == "mph" and form["precipitation_unit"] == "inch"
        return httpx.Response(200, json=[_location(float(a), 0, T0, 4) for a in lats])

    route = respx.post(URL).mock(side_effect=handler)
    points = [(30 + i * 0.01, -90.0) for i in range(250)]
    out = OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="").hourly(points, T0, T0 + timedelta(hours=3))
    assert route.call_count == 3  # batches of 100
    assert len(out) == 250
    assert out[0].rain_in[0] == pytest.approx(0.15)
    assert out[0].rain_in[-1] == pytest.approx(0.15)  # a null showers value carries the previous one


@respx.mock
def test_results_are_cached_per_point_and_window():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=_location(30, -90, T0, 3)))
    client = OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="")
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=2))
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=2))
    assert route.call_count == 1


@respx.mock
def test_rate_limit_becomes_a_user_facing_error():
    respx.post(URL).mock(return_value=httpx.Response(429, json={"reason": "limit"}))
    with pytest.raises(WeatherError, match="rate limit"):
        OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="").hourly([(30, -90)], T0, T0)


@respx.mock
def test_misaligned_time_window_is_rejected():
    respx.post(URL).mock(return_value=httpx.Response(200, json=_location(30, -90, T0 + timedelta(hours=1), 3)))
    with pytest.raises(WeatherError, match="time window"):
        OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="").hourly([(30, -90)], T0, T0)
