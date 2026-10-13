from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from common.ratelimit import parse_rate


class WeatherConfig(AppConfig):
    name = "apps.weather"
    label = "weather"

    def ready(self) -> None:
        # A malformed allowance would otherwise fail every plan instead of the deploy.
        try:
            parse_rate(settings.WEATHER_BUDGET)
        except ValueError as error:
            raise ImproperlyConfigured(f"WEATHER_BUDGET: {error}") from error
