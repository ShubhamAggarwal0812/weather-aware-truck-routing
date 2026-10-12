from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.api.views import HealthView

v1: list[URLPattern | URLResolver] = [
    path("health", HealthView.as_view(), name="health"),
    path("", include("apps.trips.urls")),
    path("", include("apps.places.urls")),
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

urlpatterns = [
    path("api/v1/", include(v1)),
]
