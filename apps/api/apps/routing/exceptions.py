from common.exceptions import ServiceError


class RoutingError(ServiceError):
    """Routing failed. 422 when no route exists, 5xx when the provider is unavailable."""

    default_status = 502
