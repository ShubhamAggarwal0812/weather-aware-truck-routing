import httpx
import respx
from rest_framework.test import APIClient

URL = "/api/v1/places"


@respx.mock
def test_search_uses_photon_without_a_tomtom_key():
    photon = respx.get("https://photon.komoot.io/api/").mock(
        return_value=httpx.Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [-104.99, 39.74]},
                        "properties": {"name": "Denver", "state": "Colorado", "countrycode": "US"},
                    },
                    {  # same label twice: deduplicated
                        "geometry": {"coordinates": [-104.98, 39.73]},
                        "properties": {"name": "Denver", "state": "Colorado", "countrycode": "US"},
                    },
                ]
            },
        )
    )
    res = APIClient().get(URL, {"q": "denver"})
    assert res.status_code == 200
    assert res.json() == {"results": [{"label": "Denver, Colorado, US", "lat": 39.74, "lon": -104.99}]}
    APIClient().get(URL, {"q": "Denver "})  # normalised query hits the cache
    assert photon.call_count == 1


def test_query_is_validated():
    res = APIClient().get(URL, {"q": "d"})
    assert res.status_code == 400
    assert "q" in res.json()["fields"]


@respx.mock
def test_upstream_failure_is_a_readable_503():
    respx.get("https://photon.komoot.io/api/").mock(return_value=httpx.Response(500))
    res = APIClient().get(URL, {"q": "denver"})
    assert res.status_code == 503
    assert res.json() == {"error": "Place search is unavailable right now."}
