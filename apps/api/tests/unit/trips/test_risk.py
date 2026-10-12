import pytest

from apps.trips.domain.risk import (
    RAIN_BANDS_IN_HR,
    SNOW_BANDS_IN_HR,
    WIND_BANDS_MPH,
    Conditions,
    RiskLevel,
    assess,
    classify,
    wind_level,
)

L, M, H, S, NT = RiskLevel


@pytest.mark.parametrize(
    ("mph", "level"),
    [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, NT), (80, NT)],
)
def test_wind_bands(mph, level):
    assert classify(mph, WIND_BANDS_MPH) == level


@pytest.mark.parametrize(
    ("rate", "level"),
    [(0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H), (0.50, S), (1.00, S), (1.001, NT)],
)
def test_rain_bands(rate, level):
    assert classify(rate, RAIN_BANDS_IN_HR) == level


@pytest.mark.parametrize(
    ("rate", "level"),
    [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, NT)],
)
def test_snow_bands(rate, level):
    assert classify(rate, SNOW_BANDS_IN_HR) == level


@pytest.mark.parametrize(
    ("mph", "load", "level", "raised"),
    [
        (55, 0, NT, False),  # >=55 is No Travel for any load
        (60, 50_000, NT, False),
        (45, 30_000, S, False),  # load rule needs strictly more than 30,000 lb
        (45, 30_001, NT, True),
        (54.9, 40_000, NT, True),
        (35, 40_000, H, False),  # needs strictly more than 40,000 lb
        (35, 40_001, S, True),
        (44.9, 79_000, S, True),
        (34.9, 79_000, M, False),  # below 35 mph no load rule applies
        (45, 20_000, S, False),
    ],
)
def test_load_rules(mph, load, level, raised):
    got, rule = wind_level(mph, load)
    assert got == level
    assert (rule is not None) == raised


def test_overall_level_is_the_worst_condition():
    a = assess(Conditions(wind_mph=30, rain_in_hr=0.3, snow_in_hr=0.0), load_lb=10_000)
    assert a.level == H
    assert [f.condition for f in a.drivers] == ["rain"]


def test_load_rule_is_reported_as_the_driver():
    a = assess(Conditions(wind_mph=38, rain_in_hr=0.0, snow_in_hr=0.0), load_lb=42_000)
    assert a.level == S
    (driver,) = a.drivers
    assert driver.condition == "wind"
    assert "40,000" in driver.load_rule


def test_ties_list_every_driver():
    a = assess(Conditions(wind_mph=36, rain_in_hr=0.3, snow_in_hr=1.2), load_lb=0)
    assert a.level == H
    assert [f.condition for f in a.drivers] == ["wind", "rain", "snow"]


def test_low_has_no_drivers():
    assert assess(Conditions(5, 0, 0), 0).drivers == ()
