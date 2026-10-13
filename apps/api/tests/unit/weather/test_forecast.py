import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from apps.weather import forecast
from apps.weather.exceptions import WeatherError
from apps.weather.forecast import HourlySeries, OpenMeteoClient, _precipitation, _scored, _short_gaps_filled

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


def _form(request):
    return {name: values[0] for name, values in parse_qs(request.content.decode()).items()}


def _window(form):
    start, end = (
        datetime.strptime(form[name], "%Y-%m-%dT%H:%M").replace(tzinfo=UTC) for name in ("start_hour", "end_hour")
    )
    return start, int((end - start) / timedelta(hours=1)) + 1


def _answer(request):
    form = _form(request)
    start, hours = _window(form)
    points = zip(form["latitude"].split(","), form["longitude"].split(","))
    return httpx.Response(
        200, json=[_location(float(latitude), float(longitude), start, hours) for latitude, longitude in points]
    )


def _client():
    return OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="")


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
def test_should_batch_points_and_sum_rain_and_showers():
    def handler(request):
        form = _form(request)
        assert form["wind_speed_unit"] == "mph"
        assert form["precipitation_unit"] == "inch"
        return _answer(request)

    route = respx.post(URL).mock(side_effect=handler)
    points = [(30 + i * 0.01, -90.0) for i in range(250)]
    out = _client().hourly(points, T0, T0 + timedelta(hours=3))
    assert route.call_count == 5  # batches of 50
    assert len(out) == 250
    assert out[0].rain_in[0] == pytest.approx(0.15)
    assert out[0].rain_in[-1] == pytest.approx(0.15)  # a null showers value carries the previous one


@respx.mock
def test_should_fetch_through_the_hour_after_the_last_sample_and_no_further():
    route = respx.post(URL).mock(side_effect=_answer)
    last_sample = T0 + timedelta(hours=30, minutes=20)
    hour_whose_total_covers_the_last_sample = T0 + timedelta(hours=31)
    (series,) = _client().hourly([(30, -90)], T0 + timedelta(minutes=10), last_sample)
    assert _window(_form(route.calls.last.request)) == (T0, 32)
    assert series.last_hour == hour_whose_total_covers_the_last_sample
    assert series.at(last_sample).rain_in_hr == pytest.approx(0.15)


@respx.mock
def test_should_reuse_a_cached_series_that_reaches_far_enough_from_the_same_start_hour():
    route = respx.post(URL).mock(side_effect=_answer)
    client = _client()
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=20))
    client.hourly([(30, -90)], T0 + timedelta(minutes=40), T0 + timedelta(hours=2))
    assert route.call_count == 1


@respx.mock
def test_should_refuse_a_window_past_the_forecast_without_asking_for_it(monkeypatch):
    route = respx.post(URL).mock(side_effect=_answer)
    last_forecast_hour = T0 + timedelta(hours=3)
    monkeypatch.setattr(forecast, "forecast_limit", lambda: last_forecast_hour)
    client = _client()
    reads_the_last_forecast_hour = last_forecast_hour - timedelta(minutes=1)
    client.hourly([(30, -90)], T0, reads_the_last_forecast_hour)
    with pytest.raises(WeatherError, match="16 days"):
        client.hourly([(31, -90)], T0, last_forecast_hour)
    assert route.call_count == 1


class RecordingBudget:
    def __init__(self, refuse: bool = False):
        self.spent: list[int] = []
        self.refuse = refuse

    def spend(self, locations):
        if self.refuse:
            raise WeatherError("allowance", status=429)
        self.spent.append(locations)


@respx.mock
def test_should_charge_the_budget_only_for_locations_it_has_to_fetch():
    respx.post(URL).mock(side_effect=_answer)
    budget = RecordingBudget()
    client = OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="", budget=budget)
    client.hourly([(30, -90), (31, -90)], T0, T0 + timedelta(hours=2))
    client.hourly([(30, -90), (31, -90), (32, -90)], T0, T0 + timedelta(hours=2))
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=1))
    assert budget.spent == [2, 1]


@respx.mock
def test_should_fetch_nothing_when_the_budget_refuses():
    route = respx.post(URL).mock(side_effect=_answer)
    client = OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="", budget=RecordingBudget(refuse=True))
    end = T0 + timedelta(hours=2)
    with pytest.raises(WeatherError, match="allowance"):
        client.hourly([(30, -90)], T0, end)
    assert route.call_count == 0


@respx.mock
def test_should_fetch_again_when_the_arrival_is_past_the_cached_series():
    route = respx.post(URL).mock(side_effect=_answer)
    client = _client()
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=2))
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=30))
    assert route.call_count == 2


@respx.mock
def test_should_turn_the_rate_limit_into_a_user_facing_error():
    respx.post(URL).mock(return_value=httpx.Response(429, json={"reason": "limit"}))
    client = _client()
    with pytest.raises(WeatherError, match="rate limit"):
        client.hourly([(30, -90)], T0, T0)


@respx.mock
def test_should_reject_a_misaligned_time_window():
    respx.post(URL).mock(return_value=httpx.Response(200, json=_location(30, -90, T0 + timedelta(hours=1), 3)))
    client = _client()
    with pytest.raises(WeatherError, match="time window"):
        client.hourly([(30, -90)], T0, T0)


@respx.mock
def test_should_reject_a_series_that_stops_short():
    def handler(request):
        start, hours = _window(_form(request))
        return httpx.Response(200, json=_location(30, -90, start, hours - 5))

    respx.post(URL).mock(side_effect=handler)
    client, end = _client(), T0 + timedelta(hours=20)
    with pytest.raises(WeatherError, match="time window"):
        client.hourly([(30, -90)], T0, end)


@respx.mock
def test_should_reject_a_response_that_leaves_out_a_variable():
    def handler(request):
        start, hours = _window(_form(request))
        location = _location(30, -90, start, hours)
        del location["hourly"]["showers"]
        return httpx.Response(200, json=location)

    respx.post(URL).mock(side_effect=handler)
    client, end = _client(), T0 + timedelta(hours=2)
    with pytest.raises(WeatherError, match="incomplete"):
        client.hourly([(30, -90)], T0, end)


@respx.mock
def test_should_reject_a_location_without_hourly_data():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"latitude": 30, "longitude": -90}))
    client = _client()
    with pytest.raises(WeatherError, match="time window"):
        client.hourly([(30, -90)], T0, T0)


def test_should_fill_short_gaps_with_the_nearest_earlier_value():
    assert _scored([None, 1.0, None, None, 2.0, None]) == (1.0, 1.0, 1.0, 1.0, 2.0, 2.0)


def test_should_reject_a_gap_longer_than_three_hours_in_a_scored_variable():
    with pytest.raises(WeatherError, match="incomplete"):
        _scored([5.0, 6.0, None, None, None, None])


def test_should_leave_a_long_gap_unknown_in_a_variable_that_is_only_shown():
    assert _short_gaps_filled([1.0, None, None, None, None, 2.0, None]) == (1.0, None, None, None, None, 2.0, 2.0)
    assert _short_gaps_filled([None, None]) == (None, None)


def test_should_read_a_precipitation_type_with_no_values_as_none_of_it():
    assert _precipitation([None, None]) == (0.0, 0.0)


def test_should_reject_a_scored_variable_with_no_values():
    with pytest.raises(WeatherError, match="incomplete"):
        _scored([None, None])


@respx.mock
def test_should_show_gusts_and_temperature_as_unknown_instead_of_failing_without_them():
    def handler(request):
        start, hours = _window(_form(request))
        location = _location(30, -90, start, hours)
        location["hourly"]["wind_gusts_10m"] = [20.0, 20.0] + [None] * (hours - 2)
        location["hourly"]["temperature_2m"] = [None] * hours
        return httpx.Response(200, json=location)

    respx.post(URL).mock(side_effect=handler)
    (series,) = _client().hourly([(30, -90)], T0, T0 + timedelta(hours=6))
    early, late = series.at(T0 + timedelta(minutes=30)), series.at(T0 + timedelta(hours=5))
    assert (early.wind_mph, early.gust_mph, early.temp_f) == (12.0, 20.0, None)
    assert (late.wind_mph, late.gust_mph) == (12.0, None)


@respx.mock
def test_should_reject_a_forecast_without_any_wind_rather_than_score_it_as_calm():
    def handler(request):
        start, hours = _window(_form(request))
        location = _location(30, -90, start, hours)
        location["hourly"]["wind_speed_10m"] = [None] * hours
        return httpx.Response(200, json=location)

    respx.post(URL).mock(side_effect=handler)
    client, end = _client(), T0 + timedelta(hours=2)
    with pytest.raises(WeatherError, match="incomplete"):
        client.hourly([(30, -90)], T0, end)


@respx.mock
def test_should_read_a_forecast_without_any_showers_as_no_showers():
    def handler(request):
        start, hours = _window(_form(request))
        location = _location(30, -90, start, hours)
        location["hourly"]["showers"] = [None] * hours
        return httpx.Response(200, json=location)

    respx.post(URL).mock(side_effect=handler)
    (series,) = _client().hourly([(30, -90)], T0, T0 + timedelta(hours=2))
    assert set(series.rain_in) == {0.1}


@respx.mock
def test_should_hedge_a_slow_batch(monkeypatch):
    monkeypatch.setattr("apps.weather.forecast.HEDGE_AFTER_S", 0.05)
    attempts = ThreadPoolExecutor(max_workers=2)
    monkeypatch.setattr("apps.weather.forecast._attempts", attempts)
    calls = []

    def handler(request):
        calls.append(time.monotonic())
        if len(calls) == 1:
            time.sleep(1.0)  # the first attempt hangs
        return _answer(request)

    respx.post(URL).mock(side_effect=handler)
    started = time.monotonic()
    out = OpenMeteoClient(base_url="https://api.open-meteo.com", api_key="").hourly(
        [(30, -90)], T0, T0 + timedelta(hours=2)
    )
    assert len(out) == 1
    assert len(calls) == 2
    assert time.monotonic() - started < 0.8  # answered by the hedge, not the slow attempt
    attempts.shutdown(wait=True)  # let the abandoned attempt finish inside the test


@respx.mock
def test_should_not_hedge_a_batch_that_only_waited_for_a_free_worker(monkeypatch):
    attempts = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr("apps.weather.forecast._attempts", attempts)
    monkeypatch.setattr("apps.weather.forecast.HEDGE_AFTER_S", 0.2)
    route = respx.post(URL).mock(side_effect=_answer)
    another_batch_holding_the_only_worker = attempts.submit(time.sleep, 0.6)
    _client().hourly([(30, -90)], T0, T0 + timedelta(hours=2))
    assert another_batch_holding_the_only_worker.done()
    attempts.shutdown(wait=True)
    assert route.call_count == 1


@respx.mock
def test_should_not_send_a_hedge_that_is_still_queued_when_the_first_attempt_answers(monkeypatch):
    attempts = ThreadPoolExecutor(max_workers=2)
    monkeypatch.setattr("apps.weather.forecast._attempts", attempts)
    monkeypatch.setattr("apps.weather.forecast.HEDGE_AFTER_S", 0.1)

    def slow_enough_to_hedge(request):
        time.sleep(0.3)
        return _answer(request)

    route = respx.post(URL).mock(side_effect=slow_enough_to_hedge)
    client = _client()
    frees_a_worker_for_the_first_attempt = attempts.submit(time.sleep, 0.2)
    time.sleep(0.05)
    busy_until_after_the_answer = attempts.submit(time.sleep, 1.0)
    client.hourly([(30, -90)], T0, T0 + timedelta(hours=2))
    attempts.shutdown(wait=True)
    assert frees_a_worker_for_the_first_attempt.done()
    assert busy_until_after_the_answer.done()
    assert route.call_count == 1
