"""Local development: `python manage.py runserver` / `make dev`."""

from .base import *  # noqa: F403  # NOSONAR

DEBUG = True
ALLOWED_HOSTS = ["*"]
