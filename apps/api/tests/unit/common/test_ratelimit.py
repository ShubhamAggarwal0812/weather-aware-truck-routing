import pytest
from django.core.cache import caches

from common.ratelimit import add_to_window, parse_rate, seconds_left, window_key


@pytest.fixture
def counters():
    cache = caches["limits"]
    cache.clear()
    return cache


@pytest.mark.parametrize(
    ("rate", "expected"),
    [("3000/day", (3000, 86_400)), ("30/min", (30, 60)), (" 5 / h ", (5, 3_600)), ("1/s", (1, 1)), ("  ", None)],
)
def test_should_read_a_rate_as_a_count_and_a_window_in_seconds(rate, expected):
    assert parse_rate(rate) == expected


@pytest.mark.parametrize("rate", ["3000", "lots/day", "-1/day", "3000/fortnight", "/day"])
def test_should_refuse_a_rate_it_cannot_read(rate):
    with pytest.raises(ValueError, match="isn't a rate like 3000/day"):
        parse_rate(rate)


def test_should_count_each_window_on_its_own(counters):
    assert add_to_window(counters, "client", 2, 60, now=119.0) == 2
    assert add_to_window(counters, "client", 3, 60, now=119.5) == 5
    assert add_to_window(counters, "client", 1, 60, now=120.0) == 1
    assert window_key("client", 60, 119.0) != window_key("client", 60, 120.0)


def test_should_count_from_the_request_when_its_counter_vanishes_between_the_two_steps(monkeypatch, counters):
    def evicted(key, delta=1, version=None):
        raise ValueError(f"Key {key!r} not found.")

    monkeypatch.setattr(counters, "incr", evicted)
    assert add_to_window(counters, "client", 4, 60, now=0.0) == 4


def test_should_give_the_seconds_left_in_the_window():
    assert seconds_left(60, now=6_045.0) == 15
