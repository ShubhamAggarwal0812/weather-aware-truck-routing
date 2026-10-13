import pytest
from django.apps import apps
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured

from apps.weather import budget as budget_module
from apps.weather.budget import WeatherBudget
from apps.weather.exceptions import WeatherError

ONE_AM_UTC = 86_400 * 20_000 + 3_600


@pytest.fixture(autouse=True)
def empty_counters():
    caches["limits"].clear()


@pytest.fixture
def clock(monkeypatch):
    now = [float(ONE_AM_UTC)]
    monkeypatch.setattr(budget_module.time, "time", lambda: now[0])
    return now


def test_should_refuse_a_client_past_its_allowance_until_the_window_resets(clock):
    budget = WeatherBudget("203.0.113.9", "100/day")
    budget.spend(60)
    budget.spend(40)
    with pytest.raises(WeatherError, match="resets at 00:00 UTC") as refused:
        budget.spend(1)
    assert refused.value.status == 429
    clock[0] += 23 * 3_600
    budget.spend(100)


def test_should_not_count_a_refused_request_so_a_smaller_one_still_fits(clock):
    budget = WeatherBudget("203.0.113.9", "100/day")
    budget.spend(70)
    with pytest.raises(WeatherError):
        budget.spend(50)
    budget.spend(30)


def test_should_count_each_client_on_its_own(clock):
    WeatherBudget("203.0.113.9", "100/day").spend(100)
    WeatherBudget("198.51.100.4", "100/day").spend(100)


def test_should_not_limit_anything_when_the_rate_is_blank(clock):
    WeatherBudget("203.0.113.9", "").spend(1_000_000)


def test_should_refuse_for_good_a_request_bigger_than_the_whole_allowance_without_counting_it(clock):
    budget = WeatherBudget("203.0.113.9", "100/day")
    with pytest.raises(WeatherError, match="more weather data than one connection may fetch") as refused:
        budget.spend(101)
    assert refused.value.status == 422
    budget.spend(100)


def test_should_fail_at_startup_when_the_allowance_is_malformed(settings):
    settings.WEATHER_BUDGET = "plenty"
    weather_app = apps.get_app_config("weather")
    with pytest.raises(ImproperlyConfigured, match="WEATHER_BUDGET"):
        weather_app.ready()
