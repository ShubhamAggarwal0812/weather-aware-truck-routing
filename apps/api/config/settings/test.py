"""pytest: no real providers, no throttling, deterministic config."""

from .base import *  # noqa: F403  # NOSONAR
from .base import REST_FRAMEWORK

TOMTOM_API_KEY = ""
ROUTING_PROVIDER = "osrm"
OPEN_METEO_API_KEY = ""
OPEN_METEO_BASE_URL = "https://api.open-meteo.com"

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"},
    "limits": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-limits"},
}
