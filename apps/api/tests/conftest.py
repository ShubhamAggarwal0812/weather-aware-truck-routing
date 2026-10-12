from datetime import UTC, datetime, timedelta

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def departure() -> datetime:
    return (datetime.now(UTC) + timedelta(hours=3)).replace(minute=20, second=0, microsecond=0)
