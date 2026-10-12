from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.routing.providers import get_routing_provider
from apps.trips.domain.risk import rules_table
from apps.trips.services.corridor import corridor_forecast
from apps.trips.services.planning import plan_trip
from apps.trips.services.presenters import present_plan
from apps.weather.forecast import OpenMeteoClient
from common.api.serializers import ErrorSerializer

from .serializers import (
    ConfigSerializer,
    CorridorRequestSerializer,
    CorridorSerializer,
    PlanRequestSerializer,
    PlanSerializer,
)

PLAN_CACHE_TTL_S = 10 * 60
ERRORS = {400: ErrorSerializer, 422: ErrorSerializer, 502: ErrorSerializer, 503: ErrorSerializer}


def _cache_key(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha1(raw.encode()).hexdigest()}"


class ConfigView(APIView):
    @extend_schema(operation_id="getConfig", responses=ConfigSerializer)
    def get(self, request: Request) -> Response:
        provider = get_routing_provider()
        return Response(
            {"routing_provider": provider.name, "truck_aware": provider.truck_aware, "rules": rules_table()}
        )


class PlanView(APIView):
    throttle_scope = "plan"

    @extend_schema(operation_id="planTrip", request=PlanRequestSerializer, responses={200: PlanSerializer, **ERRORS})
    def post(self, request: Request) -> Response:
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = _cache_key("plan", {**serializer.validated_data, "provider": settings.ROUTING_PROVIDER})
        result = cache.get(key)
        if result is None:
            plan = plan_trip(serializer.to_trip(), get_routing_provider(), OpenMeteoClient())
            result = present_plan(plan)
            cache.set(key, result, PLAN_CACHE_TTL_S)
        return Response(result)


class CorridorForecastView(APIView):
    throttle_scope = "corridor"

    @extend_schema(
        operation_id="getCorridorForecast",
        request=CorridorRequestSerializer,
        responses={200: CorridorSerializer, **ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = CorridorRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lines = [[(lat, lon) for lat, lon in line] for line in data["lines"]]
        return Response(corridor_forecast(lines, data["departure"], data["load_weight_lb"], OpenMeteoClient()))
