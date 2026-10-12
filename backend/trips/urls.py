from django.urls import path

from trips import views

urlpatterns = [
    path("config", views.ConfigView.as_view()),
    path("geocode", views.GeocodeView.as_view()),
    path("plan", views.PlanView.as_view()),
    path("corridor", views.CorridorView.as_view()),
]
