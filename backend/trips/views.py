from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from trips.domain.risk import rules_table
from trips.serializers import CorridorRequestSerializer, GeocodeQuerySerializer, PlanRequestSerializer
from trips.services import geocoding
from trips.services.http import UpstreamError
from trips.services.planner import corridor_forecast, plan_trip, routing_provider
from trips.services.routing.base import RoutingError
from trips.services.weather import OpenMeteoClient, WeatherError

log = logging.getLogger(__name__)

PLAN_CACHE_TTL_S = 10 * 60


def exception_handler(exc, context):
    """Every error leaves the API as {"error": message} (+ "fields" for validation)."""
    if isinstance(exc, ValidationError):
        return Response({"error": "Some fields are invalid.", "fields": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, RoutingError):
        return Response({"error": str(exc)}, status=exc.status)
    if isinstance(exc, (WeatherError, geocoding.GeocodingError)):
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, UpstreamError):
        log.warning("unhandled upstream error: %s", exc)
        return Response({"error": "An upstream service failed. Try again."}, status=status.HTTP_502_BAD_GATEWAY)
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and "detail" in response.data:
        response.data = {"error": str(response.data["detail"])}
    return response


def _cache_key(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha1(raw.encode()).hexdigest()}"


class ConfigView(APIView):
    def get(self, request: Request) -> Response:
        provider = routing_provider()
        return Response(
            {
                "routing_provider": provider.name,
                "truck_aware": provider.truck_aware,
                "rules": rules_table(),
            }
        )


class GeocodeView(APIView):
    throttle_scope = "geocode"

    def get(self, request: Request) -> Response:
        query = GeocodeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response({"results": geocoding.search(query.validated_data["q"])})


class PlanView(APIView):
    throttle_scope = "plan"

    def post(self, request: Request) -> Response:
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = serializer.to_trip()
        key = _cache_key("plan", {**serializer.validated_data, "provider": settings.ROUTING_PROVIDER})
        result = cache.get(key)
        if result is None:
            result = plan_trip(trip, routing_provider(), OpenMeteoClient())
            cache.set(key, result, PLAN_CACHE_TTL_S)
        return Response(result)


class CorridorView(APIView):
    throttle_scope = "corridor"

    def post(self, request: Request) -> Response:
        serializer = CorridorRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = corridor_forecast(data["lines"], data["departure"], data["load_weight_lb"], OpenMeteoClient())
        return Response(result)
