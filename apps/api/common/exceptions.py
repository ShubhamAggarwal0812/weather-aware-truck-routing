class ServiceError(Exception):
    """A failure whose message is safe to show to the user, with the HTTP status to use.

    Each app subclasses it (RoutingError, WeatherError, ...). The API's exception
    handler turns any ServiceError into ``{"error": message}`` with that status.
    """

    default_status = 503

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status or self.default_status
