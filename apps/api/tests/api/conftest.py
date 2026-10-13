from apps.trips.api import views


def install(monkeypatch, provider, weather) -> None:
    """Route the trips API through fakes instead of TomTom and Open-Meteo."""
    monkeypatch.setattr(views, "get_routing_provider", lambda: provider)
    monkeypatch.setattr(views, "_forecast_source", lambda request: weather)
