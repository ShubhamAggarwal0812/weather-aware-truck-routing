from django.urls import path

from .api.views import ConfigView, CorridorForecastView, PlanView

urlpatterns = [
    path("config", ConfigView.as_view(), name="config"),
    path("trips/plan", PlanView.as_view(), name="trip-plan"),
    path("trips/corridor-forecast", CorridorForecastView.as_view(), name="corridor-forecast"),
]
