import logging
from typing import Any

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions import ServiceError
from common.http import UpstreamError

log = logging.getLogger(__name__)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Every error leaves the API as ``{"error": message}``, plus ``"fields"`` for validation."""
    if isinstance(exc, ValidationError):
        return Response({"error": "Some fields are invalid.", "fields": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, ServiceError):
        return Response({"error": str(exc)}, status=exc.status)
    if isinstance(exc, UpstreamError):
        log.warning("unhandled upstream error: %s", exc)
        return Response({"error": "An upstream service failed. Try again."}, status=status.HTTP_502_BAD_GATEWAY)
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and "detail" in response.data:
        response.data = {"error": str(response.data["detail"])}
    return response
