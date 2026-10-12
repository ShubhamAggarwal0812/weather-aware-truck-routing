"""The responses the presenters build must match the serializers that define the OpenAPI schema.

The frontend's TypeScript types are generated from that schema, so a mismatch
here is a mismatch between what the UI is typed against and what it receives.
"""

from pathlib import Path

import pytest
import yaml
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.trips.api.serializers import ConfigSerializer, CorridorSerializer, PlanSerializer
from tests.fakes import FakeProvider, FakeWeather, storm, straight_route

from .conftest import install
from .test_plan import DEST, ORIGIN, body

API_DIR = Path(__file__).resolve().parents[2]


def assert_matches(serializer_class, data):
    serializer = serializer_class(data=data)
    assert serializer.is_valid(), serializer.errors
    # Nothing in the response that the schema doesn't declare.
    declared = set(serializer_class().fields)
    assert set(data) == declared


def test_plan_response_matches_schema(monkeypatch, departure):
    routes = [straight_route(ORIGIN, DEST), straight_route(ORIGIN, DEST, via=(41.6, -100.0))]
    install(monkeypatch, FakeProvider(routes), FakeWeather(storm))
    data = APIClient().post("/api/v1/trips/plan", body(departure), format="json").json()
    assert_matches(PlanSerializer, data)


def test_corridor_response_matches_schema(monkeypatch, departure):
    install(monkeypatch, FakeProvider([]), FakeWeather(storm))
    payload = {"lines": [[[40.0, -105.0], [40.0, -95.0]]], "departure": departure.isoformat(), "load_weight_lb": 0}
    data = APIClient().post("/api/v1/trips/corridor-forecast", payload, format="json").json()
    assert_matches(CorridorSerializer, data)


def test_config_response_matches_schema():
    assert_matches(ConfigSerializer, APIClient().get("/api/v1/config").json())


@pytest.mark.filterwarnings("ignore")
def test_committed_schema_is_current(tmp_path):
    """openapi.yaml (and the TS types built from it) must be regenerated after API changes: `make schema`."""
    out = tmp_path / "openapi.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    committed = API_DIR / "openapi.yaml"
    assert committed.exists(), "run `make schema`"
    assert yaml.safe_load(out.read_text()) == yaml.safe_load(committed.read_text()), "run `make schema`"
