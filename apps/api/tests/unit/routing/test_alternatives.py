from datetime import UTC, datetime

from apps.routing.alternatives import distinct_routes, three_routes
from apps.routing.providers import RouteRequest
from tests.fakes import FakeProvider, straight_route

ORIGIN, DEST = (40.0, -105.0), (40.0, -95.0)
REQUEST = RouteRequest(ORIGIN, DEST, datetime(2026, 10, 13, tzinfo=UTC), 75_000)


def test_provider_alternatives_are_used_when_there_are_three():
    routes = [
        straight_route(ORIGIN, DEST),
        straight_route(ORIGIN, DEST, via=(41.5, -100)),
        straight_route(ORIGIN, DEST, via=(38.5, -100)),
    ]
    provider = FakeProvider(routes, via=lambda v: straight_route(ORIGIN, DEST, via=v))
    assert three_routes(provider, REQUEST) == routes
    # The first two detours go out with the main request, but no second round follows.
    assert len(provider.via_calls) == 2


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


def test_no_routes_means_no_second_round():
    provider = FakeProvider([])
    assert three_routes(provider, REQUEST) == []
    assert len(provider.via_calls) == 2


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
