from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness probe. Doesn't touch upstream services."""

    @extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}))
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})
