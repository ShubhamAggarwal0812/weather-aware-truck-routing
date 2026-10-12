from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.places import services
from common.api.serializers import ErrorSerializer

from .serializers import PlaceQuerySerializer, PlaceSearchResponseSerializer


class PlaceSearchView(APIView):
    throttle_scope = "places"

    @extend_schema(
        operation_id="searchPlaces",
        parameters=[OpenApiParameter("q", str, required=True, description="Free text, at least 2 characters.")],
        responses={200: PlaceSearchResponseSerializer, 400: ErrorSerializer, 503: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        query = PlaceQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response({"results": services.search(query.validated_data["q"])})
