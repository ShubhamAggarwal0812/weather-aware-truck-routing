from django.conf import settings

from .base import Route, RouteRequest, RoutingProvider
from .osrm import OSRMProvider
from .tomtom import TomTomProvider

__all__ = ["OSRMProvider", "Route", "RouteRequest", "RoutingProvider", "TomTomProvider", "get_routing_provider"]


def get_routing_provider() -> RoutingProvider:
    """TomTom (truck-aware) when a key is configured, else the public OSRM server (car profile)."""
    if settings.ROUTING_PROVIDER == "tomtom" and settings.TOMTOM_API_KEY:
        return TomTomProvider(settings.TOMTOM_API_KEY)
    return OSRMProvider(settings.OSRM_BASE_URL)
