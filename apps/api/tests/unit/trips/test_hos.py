import pytest

from apps.trips.domain import hos

H = 3600


@pytest.mark.parametrize(
    ("drive_h", "elapsed_h"),
    [
        (0, 0),
        (5, 5),
        (8, 8),  # break only starts if driving continues
        (9, 9.5),
        (11, 11.5),  # arriving at the limit doesn't pay for the rest after it
        (12, 22.5),  # 11h + 0.5h break + 10h rest + 1h
        (19, 29.5),  # second cycle's 8h mark, still no second break
        (20, 31),
        (22, 33),
        (23, 44),
    ],
)
def test_elapsed_with_breaks(drive_h, elapsed_h):
    assert hos.elapsed_s(drive_h * H) == pytest.approx(elapsed_h * H)


def test_elapsed_without_breaks():
    assert hos.elapsed_s(30 * H, breaks=False) == 30 * H


@pytest.mark.parametrize("drive_h", [0.5, 3, 7.99, 8.5, 10, 11.2, 15, 19.5, 30])
def test_drive_at_is_the_inverse_while_driving(drive_h):
    drive, activity = hos.drive_s_at(hos.elapsed_s(drive_h * H))
    assert activity == "driving"
    assert drive == pytest.approx(drive_h * H)


@pytest.mark.parametrize(
    ("elapsed_h", "drive_h", "activity"),
    [(8.25, 8, "break"), (12, 11, "rest"), (21.4, 11, "rest"), (21.5, 11, "driving"), (22, 11.5, "driving")],
)
def test_drive_at_during_stops(elapsed_h, drive_h, activity):
    drive, got = hos.drive_s_at(elapsed_h * H)
    assert got == activity
    assert drive == pytest.approx(drive_h * H)


def test_stops_for_a_long_trip():
    stops = hos.stops(25 * H)
    assert [(s.kind, s.drive_s / H, s.start_elapsed_s / H) for s in stops] == [
        ("break", 8, 8),
        ("rest", 11, 11.5),
        ("break", 19, 29.5),
        ("rest", 22, 33),
    ]


def test_no_stops_for_short_trips_or_when_disabled():
    assert hos.stops(8 * H) == []
    assert hos.stops(30 * H, breaks=False) == []
