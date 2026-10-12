from common.exceptions import ServiceError


class WeatherError(ServiceError):
    """The forecast couldn't be fetched or doesn't cover the trip."""

    default_status = 503
