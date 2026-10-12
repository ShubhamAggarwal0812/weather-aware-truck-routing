from rest_framework.test import APIClient, APIRequestFactory

from common.api.throttling import SharedScopedRateThrottle


def test_health():
    assert APIClient().get("/api/v1/health").json() == {"status": "ok"}


def test_config_reports_the_rules():
    client = APIClient()
    data = client.get("/api/v1/config").json()
    assert [lvl["key"] for lvl in data["rules"]["levels"]] == ["low", "moderate", "high", "severe", "no_travel"]
    assert data["rules"]["rain_in_hr"][-1] == {"level": "no_travel", "threshold": 1.0, "inclusive": False}


def test_should_key_rate_limits_on_the_address_the_proxy_saw_not_on_what_the_client_sent():
    spoofed = APIRequestFactory().post("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9", REMOTE_ADDR="172.18.0.3")
    honest = APIRequestFactory().post("/", HTTP_X_FORWARDED_FOR="203.0.113.9", REMOTE_ADDR="172.18.0.3")
    throttle = SharedScopedRateThrottle()
    assert throttle.get_ident(spoofed) == throttle.get_ident(honest) == "203.0.113.9"
