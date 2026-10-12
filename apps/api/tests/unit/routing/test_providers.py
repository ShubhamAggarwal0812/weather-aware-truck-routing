from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from apps.routing.exceptions import RoutingError
from apps.routing.providers import OSRMProvider, RouteRequest, TomTomProvider

FUTURE = datetime.now(UTC) + timedelta(hours=5)
REQUEST = RouteRequest((39.74, -104.99), (41.88, -87.63), FUTURE, 77_000)


def tomtom_route(offset=0.0):
    pts = [{"latitude": 39.74 + i * 0.1 + offset, "longitude": -104.99 + i * 0.8} for i in range(21)]
    return {
        "summary": {"lengthInMeters": 1_600_000, "travelTimeInSeconds": 60_000},
        "legs": [{"points": pts}],
        "progress": [
            {"pointIndex": 0, "distanceInMeters": 0, "travelTimeInSeconds": 0},
            {"pointIndex": 10, "distanceInMeters": 800_000, "travelTimeInSeconds": 20_000},  # fast first half
            {"pointIndex": 20, "distanceInMeters": 1_600_000, "travelTimeInSeconds": 60_000},
        ],
        "sections": [
            {
                "sectionType": "IMPORTANT_ROAD_STRETCH",
                "startPointIndex": 0,
                "endPointIndex": 15,
                "roadNumbers": [{"text": "I-80"}],
            },
            {
                "sectionType": "IMPORTANT_ROAD_STRETCH",
                "startPointIndex": 15,
                "endPointIndex": 20,
                "roadNumbers": [{"text": "I-88"}],
            },
            {
                "sectionType": "IMPORTANT_ROAD_STRETCH",
                "startPointIndex": 0,
                "endPointIndex": 2,
                "streetName": {"text": "Colfax Ave"},
            },
        ],
    }


@respx.mock
def test_tomtom_truck_request_and_parsing():
    route = respx.get(url__startswith="https://api.tomtom.com/routing/1/calculateRoute/").mock(
        return_value=httpx.Response(200, json={"routes": [tomtom_route(), tomtom_route(0.3)]})
    )
    routes = TomTomProvider("k").routes(REQUEST, alternatives=2)
    params = route.calls.last.request.url.params
    assert params["travelMode"] == "truck"
    assert params["vehicleMaxSpeed"] == "105"  # speed-governed truck, not car speeds
    assert params["vehicleWeight"] == str(round(77_000 * 0.45359237))
    assert params["maxAlternatives"] == "2"
    assert params.get_list("extendedRouteRepresentation") == ["distance", "travelTime"]
    assert params["departAt"].startswith(FUTURE.strftime("%Y-%m-%dT%H"))

    r = routes[0]
    assert len(routes) == 2
    assert r.distance_m == pytest.approx(1_600_000)
    assert r.drive_s == pytest.approx(60_000)
    # The profile follows TomTom's per-point times, not an average speed.
    assert r.drive_s_at(r.cum_distance_m[10]) == pytest.approx(20_000)
    assert r.drive_s_at(r.cum_distance_m[5]) == pytest.approx(10_000, rel=0.01)
    assert r.summary == "via I-80, I-88"


@respx.mock
def test_tomtom_via_uses_a_circle_waypoint():
    route = respx.get(url__startswith="https://api.tomtom.com/").mock(
        return_value=httpx.Response(200, json={"routes": [tomtom_route()]})
    )
    r = TomTomProvider("k").route_via(REQUEST, (40.5, -96.0))
    assert "circle(40.50000,-96.00000,15000)" in str(route.calls.last.request.url)
    assert r.via == (40.5, -96.0)


def test_tomtom_departs_now_when_departure_is_not_in_the_future():
    from apps.routing.providers.tomtom import _depart_param

    assert _depart_param(datetime.now(UTC)) == "now"


@respx.mock
@pytest.mark.parametrize(
    ("status", "body", "message", "code"),
    [
        (400, '{"error":{"description":"Engine error: NO_ROUTE_FOUND"}}', "No truck route", 422),
        (403, "{}", "API key", 502),
        (429, "{}", "quota", 503),
    ],
)
def test_should_turn_tomtom_errors_into_routing_errors(status, body, message, code):
    respx.get(url__startswith="https://api.tomtom.com/").mock(return_value=httpx.Response(status, text=body))
    provider = TomTomProvider("k")
    with pytest.raises(RoutingError, match=message) as err:
        provider.routes(REQUEST, alternatives=2)
    assert err.value.status == code


@respx.mock
def test_osrm_parsing_uses_segment_durations():
    coords = [[-104.99 + i, 39.74] for i in range(4)]
    respx.get(url__startswith="https://router.example/route/v1/driving/").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 3000.0,
                        "duration": 400.0,
                        "geometry": {"coordinates": coords},
                        "legs": [
                            {
                                "summary": "I 70",
                                "annotation": {"distance": [1000, 1000, 1000], "duration": [50, 50, 300]},
                            }
                        ],
                    }
                ],
            },
        )
    )
    (r,) = OSRMProvider("https://router.example").routes(REQUEST, alternatives=2)
    assert r.drive_s_at(r.distance_m * 2 / 3) == pytest.approx(100, rel=0.01)
    assert r.summary == "via I 70"


@respx.mock
def test_tomtom_only_sends_alternative_type_with_alternatives():
    # TomTom answers 400 "maxAlternative must be greater than 0 when alternativeType is set".
    route = respx.get(url__startswith="https://api.tomtom.com/").mock(
        return_value=httpx.Response(200, json={"routes": [tomtom_route()]})
    )
    TomTomProvider("k").route_via(REQUEST, (40.5, -96.0))
    params = route.calls.last.request.url.params
    assert params["maxAlternatives"] == "0"
    assert "alternativeType" not in params

    TomTomProvider("k").routes(REQUEST, alternatives=2)
    assert route.calls.last.request.url.params["alternativeType"] == "anyRoute"
