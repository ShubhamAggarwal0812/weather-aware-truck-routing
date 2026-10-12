from apps.trips.domain.recommend import RouteScore, compare, rank
from apps.trips.domain.risk import RiskLevel
from common.geo import METERS_PER_MILE

L, M, H, S, NT = RiskLevel
HOUR = 3600


def score(route_id, travel_h=10, **miles):
    keys = {"low": L, "moderate": M, "high": H, "severe": S, "no_travel": NT}
    meters = {level: 0.0 for level in RiskLevel}
    for key, value in miles.items():
        meters[keys[key]] = value * METERS_PER_MILE
    return RouteScore(route_id, meters, travel_h * HOUR)


def ids(scores):
    return [s.route_id for s in rank(scores)]


def test_fewest_severe_miles_wins_over_everything_after_it():
    a = score("A", travel_h=8, low=100, severe=5)
    b = score("B", travel_h=14, low=50, high=60, severe=0)
    assert ids([a, b]) == ["B", "A"]
    assert compare(rank([a, b])[0], a).criterion == "severe_miles"


def test_then_fewest_high_miles():
    a = score("A", travel_h=8, low=90, high=10)
    b = score("B", travel_h=12, low=50, moderate=50, high=0)
    assert ids([a, b]) == ["B", "A"]


def test_then_lowest_average_risk():
    a = score("A", travel_h=8, low=50, moderate=50)
    b = score("B", travel_h=9, low=90, moderate=10)
    assert ids([a, b]) == ["B", "A"]
    assert compare(b, a).criterion == "average_risk"


def test_then_shortest_travel_time():
    a = score("A", travel_h=11, low=100)
    b = score("B", travel_h=10, low=120)
    assert ids([a, b]) == ["B", "A"]
    c = compare(b, a)
    assert (c.criterion, c.recommended_value, c.other_value) == ("travel_time", 10 * HOUR, 11 * HOUR)


def test_no_travel_miles_rank_before_severe():
    a = score("A", low=100, no_travel=1)
    b = score("B", low=50, severe=40)
    assert ids([a, b]) == ["B", "A"]
    assert compare(b, a).criterion == "no_travel_miles"


def test_sub_tenth_of_a_mile_differences_fall_through_to_time():
    a = score("A", travel_h=9, low=100, severe=3.02)
    b = score("B", travel_h=10, low=100, severe=3.01)
    assert ids([a, b]) == ["A", "B"]


def test_average_risk_is_distance_weighted():
    s = score("A", low=75, severe=25)
    assert s.average_risk == 0.75


def test_full_tie_keeps_provider_order():
    a, b = score("A", low=100), score("B", low=100)
    assert ids([a, b]) == ["A", "B"]
    assert compare(a, b).criterion == "tie"
