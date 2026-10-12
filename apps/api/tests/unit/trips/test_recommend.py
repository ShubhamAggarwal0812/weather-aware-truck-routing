from apps.trips.domain.recommend import RouteScore, recommend
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
    return [ranked.route_id for ranked in recommend(scores)[0]]


def comparison_for(scores, route_id):
    return next(comparison for comparison in recommend(scores)[1] if comparison.route_id == route_id)


def test_should_rank_fewest_severe_miles_above_everything_after_it():
    a = score("A", travel_h=8, low=100, severe=5)
    b = score("B", travel_h=14, low=50, high=60, severe=0)
    assert ids([a, b]) == ["B", "A"]
    assert comparison_for([a, b], "A").criterion == "severe_miles"


def test_then_fewest_high_miles():
    a = score("A", travel_h=8, low=90, high=10)
    b = score("B", travel_h=12, low=50, moderate=50, high=0)
    assert ids([a, b]) == ["B", "A"]


def test_should_rank_lowest_average_risk_next():
    a = score("A", travel_h=8, low=50, moderate=50)
    b = score("B", travel_h=9, low=90, moderate=10)
    assert ids([a, b]) == ["B", "A"]
    assert comparison_for([a, b], "A").criterion == "average_risk"


def test_should_rank_shortest_travel_time_last():
    a = score("A", travel_h=11, low=100)
    b = score("B", travel_h=10, low=120)
    assert ids([a, b]) == ["B", "A"]
    comparison = comparison_for([a, b], "A")
    assert (comparison.criterion, comparison.recommended_value, comparison.other_value) == (
        "travel_time",
        10 * HOUR,
        11 * HOUR,
    )


def test_should_rank_no_travel_miles_before_severe_miles():
    a = score("A", low=100, no_travel=1)
    b = score("B", low=50, severe=40)
    assert ids([a, b]) == ["B", "A"]
    assert comparison_for([a, b], "A").criterion == "no_travel_miles"


def test_should_rank_any_no_travel_below_none_even_within_the_tolerance():
    faster_with_no_travel = score("A", travel_h=8, low=500, no_travel=50 / METERS_PER_MILE)
    slower_without = score("B", travel_h=9, low=500)
    routes = [faster_with_no_travel, slower_without]
    assert ids(routes) == ["B", "A"]
    comparison = comparison_for(routes, "A")
    assert (comparison.criterion, comparison.recommended_value, comparison.other_value) == ("no_travel_miles", 0, 0.03)


def test_sub_tenth_of_a_mile_differences_fall_through_to_time():
    a = score("A", travel_h=9, low=100, severe=3.02)
    b = score("B", travel_h=10, low=100, severe=3.01)
    assert ids([a, b]) == ["A", "B"]


def test_should_tie_values_a_hair_apart_that_rounding_to_a_tenth_would_split():
    slower = score("A", travel_h=13, low=100, severe=0.149)
    faster = score("B", travel_h=10, low=100, severe=0.151)
    assert ids([slower, faster]) == ["B", "A"]
    assert comparison_for([slower, faster], "A").criterion == "travel_time"


def test_should_tie_values_less_than_a_tenth_of_a_mile_apart():
    slower = score("A", travel_h=13, low=100, severe=0.051)
    faster = score("B", travel_h=10, low=100, severe=0.149)
    assert ids([slower, faster]) == ["B", "A"]


def test_should_not_tie_values_a_tenth_of_a_mile_or_more_apart():
    slower_with_less_severe = score("A", travel_h=13, low=100, severe=0.05)
    faster_with_more_severe = score("B", travel_h=10, low=100, severe=0.16)
    routes = [slower_with_less_severe, faster_with_more_severe]
    assert ids(routes) == ["A", "B"]
    assert comparison_for(routes, "B").criterion == "severe_miles"


def test_should_explain_a_route_by_the_criterion_that_ruled_it_out_against_the_leader():
    no_severe = score("A", travel_h=12, low=100, severe=0.0)
    within_tolerance = score("B", travel_h=11, low=100, severe=0.09)
    past_tolerance_of_the_leader = score("C", travel_h=8, low=100, severe=0.12)
    ranking, comparisons = recommend([no_severe, within_tolerance, past_tolerance_of_the_leader])
    assert [ranked.route_id for ranked in ranking] == ["B", "A", "C"]
    by_route = {comparison.route_id: comparison for comparison in comparisons}
    assert by_route["A"].criterion == "travel_time"
    assert by_route["C"].criterion == "severe_miles"
    assert by_route["C"].recommended_value < by_route["C"].other_value


def test_should_tie_travel_times_less_than_a_minute_apart():
    first = score("A", travel_h=10, low=100)
    twenty_seconds_faster = score("B", travel_h=10 - 20 / HOUR, low=100)
    assert ids([first, twenty_seconds_faster]) == ["A", "B"]
    assert comparison_for([first, twenty_seconds_faster], "B").criterion == "tie"


def test_average_risk_is_distance_weighted():
    s = score("A", low=75, severe=25)
    assert s.average_risk == 0.75


def test_should_keep_the_provider_order_on_a_full_tie():
    a, b = score("A", low=100), score("B", low=100)
    assert ids([a, b]) == ["A", "B"]
    assert comparison_for([a, b], "B").criterion == "tie"


def test_should_list_comparisons_in_ranking_order():
    slowest = score("A", travel_h=12, low=100)
    fastest = score("B", travel_h=10, low=100)
    middle = score("C", travel_h=11, low=100)
    ranking, comparisons = recommend([slowest, fastest, middle])
    assert [ranked.route_id for ranked in ranking] == ["B", "C", "A"]
    assert [comparison.route_id for comparison in comparisons] == ["C", "A"]


def test_should_return_no_ranking_and_no_comparisons_for_no_routes():
    assert recommend([]) == ([], [])
