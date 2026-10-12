"""Settings shared by every environment.

The API is stateless: no database, no sessions, no auth. Provider responses and
rate-limit counters live in the cache.
"""

import os
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines from a local .env (never committed). Real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


# The repo-root .env in a checkout (apps/api -> repo root); nothing in a container.
for directory in [API_DIR, *list(API_DIR.parents)[:2]]:
    load_dotenv(directory / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = False
# Nothing is signed (no sessions, no auth), but Django needs a key to start.
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-key-nothing-is-signed")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.staticfiles",  # Swagger UI assets
    "rest_framework",
    "drf_spectacular",
    "apps.routing",
    "apps.weather",
    "apps.places",
    "apps.trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

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
STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "plan": env("THROTTLE_PLAN", "30/min"),
        "corridor": env("THROTTLE_CORRIDOR", "30/min"),
        "places": env("THROTTLE_PLACES", "120/min"),
    },
    "EXCEPTION_HANDLER": "common.api.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Weather-Aware Truck Routing API",
    "DESCRIPTION": (
        "Three truck routes, weather at each checkpoint's ETA, load-aware risk, and a 48-hour corridor forecast."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Pinned so the docs page doesn't change under us.
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.2",
    "SWAGGER_UI_FAVICON_HREF": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.2/favicon-32x32.png",
    "ENUM_NAME_OVERRIDES": {
        "RiskLevelEnum": "apps.trips.api.serializers.RISK_KEYS",
        "ConditionEnum": "apps.trips.api.serializers.CONDITIONS",
    },
}

# Third-party providers. Without a TomTom key the app falls back to the public
# OSRM demo server (car profile) and Photon geocoding, so it still runs.
TOMTOM_API_KEY = env("TOMTOM_API_KEY")
ROUTING_PROVIDER = env("ROUTING_PROVIDER", "tomtom" if TOMTOM_API_KEY else "osrm")
OSRM_BASE_URL = env("OSRM_BASE_URL", "https://router.project-osrm.org")
PHOTON_BASE_URL = env("PHOTON_BASE_URL", "https://photon.komoot.io")
# The free Open-Meteo tier allows ~10k location-forecasts a day per IP. A paid key
# switches to the customer endpoint with no other change.
OPEN_METEO_API_KEY = env("OPEN_METEO_API_KEY")
OPEN_METEO_BASE_URL = env(
    "OPEN_METEO_BASE_URL",
    "https://customer-api.open-meteo.com" if OPEN_METEO_API_KEY else "https://api.open-meteo.com",
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    # httpx logs full request URLs at INFO, and TomTom URLs carry the API key.
    "loggers": {
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
