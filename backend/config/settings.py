"""Django settings.

The API is stateless: no database, no sessions, no auth. Everything that needs
to survive between requests (provider responses, rate-limit counters) lives in
the cache, which is per-process memory by default.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Local development convenience: KEY=VALUE lines from backend/.env (never committed)."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", default=False)
# Nothing is signed (no sessions, no auth), but Django requires a key to boot.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-key-nothing-is-signed")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.vercel.app")

INSTALLED_APPS = [
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES: dict = {}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truck-routing",
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
}

USE_TZ = True
TIME_ZONE = "UTC"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "plan": os.environ.get("THROTTLE_PLAN", "30/min"),
        "corridor": os.environ.get("THROTTLE_CORRIDOR", "30/min"),
        "geocode": os.environ.get("THROTTLE_GEOCODE", "120/min"),
    },
    "EXCEPTION_HANDLER": "trips.views.exception_handler",
}

# Third-party providers. Without a TomTom key the app falls back to the public
# OSRM demo server (car profile) and Photon geocoding, so it still runs locally.
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
ROUTING_PROVIDER = os.environ.get("ROUTING_PROVIDER", "tomtom" if TOMTOM_API_KEY else "osrm")
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
# The free Open-Meteo tier allows ~10k location-forecasts a day per IP. A paid key
# switches to the customer endpoint with no other change.
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
OPEN_METEO_BASE_URL = os.environ.get(
    "OPEN_METEO_BASE_URL",
    "https://customer-api.open-meteo.com" if OPEN_METEO_API_KEY else "https://api.open-meteo.com",
)
PHOTON_BASE_URL = os.environ.get("PHOTON_BASE_URL", "https://photon.komoot.io")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    # httpx logs full request URLs at INFO, and TomTom URLs carry the API key.
    "loggers": {
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
