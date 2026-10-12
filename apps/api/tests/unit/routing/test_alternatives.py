import time
from datetime import UTC, datetime

import pytest

from apps.routing.alternatives import MAX_SPUR_METERS, distinct_routes, spur_length_meters, three_routes
from apps.routing.exceptions import RoutingError
from apps.routing.providers import RouteRequest
from tests.fakes import FakeProvider, straight_route

ORIGIN, DEST = (40.0, -105.0), (40.0, -95.0)
REQUEST = RouteRequest(ORIGIN, DEST, datetime(2026, 10, 13, tzinfo=UTC), 75_000)


def test_should_use_the_provider_alternatives_when_there_are_three():
    routes = [
        straight_route(ORIGIN, DEST),
        straight_route(ORIGIN, DEST, via=(41.5, -100)),
        straight_route(ORIGIN, DEST, via=(38.5, -100)),
    ]
    provider = FakeProvider(routes, via=lambda v: straight_route(ORIGIN, DEST, via=v))
    assert three_routes(provider, REQUEST) == routes
    # At most two, not exactly two: the first-round detours aren't waited for once three routes are in.
    assert len(provider.via_calls) <= 2


def test_detours_fill_in_missing_alternatives():
    provider = FakeProvider([straight_route(ORIGIN, DEST)], via=lambda v: straight_route(ORIGIN, DEST, via=v))
    routes = three_routes(provider, REQUEST)
    assert len(routes) == 3
    assert all(r.notes for r in routes[1:])
    # The detours go to opposite sides of the fastest route.
    assert (routes[1].via[0] - 40) * (routes[2].via[0] - 40) < 0


def test_too_slow_detours_are_rejected():
    provider = FakeProvider([straight_route(ORIGIN, DEST)], via=lambda v: straight_route(ORIGIN, DEST, via=v, mph=20))
    assert len(three_routes(provider, REQUEST)) == 1


def test_duplicate_routes_are_dropped():
    a = straight_route(ORIGIN, DEST)
    b = straight_route(ORIGIN, DEST, mph=55)  # same road, different speed
    c = straight_route(ORIGIN, DEST, via=(41.5, -100))
    assert distinct_routes([a, b, c], 3) == [a, c]


def test_should_not_send_a_second_round_when_there_are_no_routes():
    provider = FakeProvider([])
    assert three_routes(provider, REQUEST) == []
    # At most two, not exactly two: the first-round detours aren't waited for once the main request has no route.
    assert len(provider.via_calls) <= 2


def test_second_round_when_first_detours_are_unusable():
    calls = []

    def via(v):
        calls.append(v)
        # First-round detours retrace the fastest route; later ones are genuinely different.
        return straight_route(ORIGIN, DEST) if len(calls) <= 2 else straight_route(ORIGIN, DEST, via=v)

    provider = FakeProvider([straight_route(ORIGIN, DEST)], via=via)
    routes = three_routes(provider, REQUEST)
    assert len(routes) == 3
    assert len(provider.via_calls) == 6


def test_should_measure_no_spur_on_a_route_without_a_via_point():
    assert spur_length_meters(straight_route(ORIGIN, DEST)) == 0


def test_should_measure_less_than_the_limit_for_an_ordinary_turn_at_the_via_point():
    assert spur_length_meters(straight_route(ORIGIN, DEST, via=(41.5, -100))) < MAX_SPUR_METERS


def test_should_measure_the_road_driven_out_and_back_to_a_dead_end_via_point():
    junction, dead_end = (40.0, -100.0), (40.1, -100.0)
    route = straight_route(ORIGIN, DEST, through=[junction, dead_end, junction], via=dead_end)
    assert 10_000 < spur_length_meters(route) < 12_500


def test_should_reject_a_detour_that_doubles_back_to_its_via_point():
    def via(via_point):
        dead_end = (via_point[0] + 0.3, via_point[1])
        return straight_route(ORIGIN, DEST, through=[via_point, dead_end, via_point], via=dead_end)

    provider = FakeProvider([straight_route(ORIGIN, DEST)], via=via)
    assert len(three_routes(provider, REQUEST)) == 1


def test_should_leave_out_a_detour_that_fails_with_an_unexpected_error():
    def via(via_point):
        raise KeyError("legs")

    provider = FakeProvider([straight_route(ORIGIN, DEST)], via=via)
    assert len(three_routes(provider, REQUEST)) == 1


def test_should_not_wait_for_the_detours_when_the_main_request_fails():
    class NoRoute(FakeProvider):
        def routes(self, request, *, alternatives):
            raise RoutingError("No route was found between these places.", status=422)

    def slow_via(via_point):
        time.sleep(1.0)
        return None

    provider = NoRoute([], via=slow_via)
    started = time.monotonic()
    with pytest.raises(RoutingError):
        three_routes(provider, REQUEST)
    assert time.monotonic() - started < 0.5
