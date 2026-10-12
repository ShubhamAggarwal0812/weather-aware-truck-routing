"""Production (Vercel functions or the Docker image). Behind a TLS-terminating proxy."""

from .base import *  # noqa: F403  # NOSONAR
from .base import env_bool, env_list

DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ".vercel.app,localhost,127.0.0.1")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# TLS is terminated by the platform; the Docker image serves plain HTTP behind nginx.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
