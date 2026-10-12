from rest_framework.test import APIClient


def test_health():
    assert APIClient().get("/api/v1/health").json() == {"status": "ok"}


def test_config_reports_the_rules():
    client = APIClient()
    data = client.get("/api/v1/config").json()
    assert [lvl["key"] for lvl in data["rules"]["levels"]] == ["low", "moderate", "high", "severe", "no_travel"]
    assert data["rules"]["rain_in_hr"][-1] == {"level": "no_travel", "threshold": 1.0, "inclusive": False}
