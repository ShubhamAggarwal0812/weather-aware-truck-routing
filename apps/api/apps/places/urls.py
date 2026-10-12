from django.urls import path

from .api.views import PlaceSearchView

urlpatterns = [
    path("places", PlaceSearchView.as_view(), name="place-search"),
]
