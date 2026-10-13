import pytest

from apps.trips.domain.recommend import recommend
from common.geo import METERS_PER_MILE
from tests.fakes import route_score

HOUR = 3600


def ids(scores):
    return [ranked.route_id for ranked in recommend(scores)[0]]


def comparison_for(scores, route_id):
    return next(comparison for comparison in recommend(scores)[1] if comparison.route_id == route_id)


def test_should_rank_fewest_severe_miles_above_everything_after_it():
    route_a = route_score("A", travel_hours=8, low=100, severe=5)
    route_b = route_score("B", travel_hours=14, low=50, high=60, severe=0)
    assert ids([route_a, route_b]) == ["B", "A"]
    assert comparison_for([route_a, route_b], "A").criterion == "severe_miles"


def test_should_rank_fewest_high_miles_next():
    route_a = route_score("A", travel_hours=8, low=90, high=10)
    route_b = route_score("B", travel_hours=12, low=50, moderate=50, high=0)
    assert ids([route_a, route_b]) == ["B", "A"]


def test_should_rank_lowest_average_risk_next():
    route_a = route_score("A", travel_hours=8, low=50, moderate=50)
    route_b = route_score("B", travel_hours=9, low=90, moderate=10)
    assert ids([route_a, route_b]) == ["B", "A"]
    assert comparison_for([route_a, route_b], "A").criterion == "average_risk"


def test_should_rank_shortest_travel_time_last():
    route_a = route_score("A", travel_hours=11, low=100)
    route_b = route_score("B", travel_hours=10, low=120)
    assert ids([route_a, route_b]) == ["B", "A"]
    comparison = comparison_for([route_a, route_b], "A")
    assert (comparison.criterion, comparison.leader_id, comparison.leader_value, comparison.value) == (
        "travel_time",
        "B",
        10 * HOUR,
        11 * HOUR,
    )


def test_should_rank_no_travel_miles_before_severe_miles():
    route_a = route_score("A", low=100, no_travel=1)
    route_b = route_score("B", low=50, severe=40)
    assert ids([route_a, route_b]) == ["B", "A"]
    assert comparison_for([route_a, route_b], "A").criterion == "no_travel_miles"


def test_should_rank_any_no_travel_below_none_even_within_the_tolerance():
    faster_with_no_travel = route_score("A", travel_hours=8, low=500, no_travel=50 / METERS_PER_MILE)
    slower_without = route_score("B", travel_hours=9, low=500)
    routes = [faster_with_no_travel, slower_without]
    assert ids(routes) == ["B", "A"]
    comparison = comparison_for(routes, "A")
    assert (comparison.criterion, comparison.leader_value) == ("no_travel_miles", 0)
    assert comparison.value == pytest.approx(50 / METERS_PER_MILE)


def test_should_let_travel_time_decide_when_miles_differ_by_less_than_a_tenth():
    route_a = route_score("A", travel_hours=9, low=100, severe=3.02)
    route_b = route_score("B", travel_hours=10, low=100, severe=3.01)
    assert ids([route_a, route_b]) == ["A", "B"]


def test_should_tie_values_a_hair_apart_that_rounding_to_a_tenth_would_split():
    slower = route_score("A", travel_hours=13, low=100, severe=0.149)
    faster = route_score("B", travel_hours=10, low=100, severe=0.151)
    assert ids([slower, faster]) == ["B", "A"]
    assert comparison_for([slower, faster], "A").criterion == "travel_time"


def test_should_tie_values_less_than_a_tenth_of_a_mile_apart():
    slower = route_score("A", travel_hours=13, low=100, severe=0.051)
    faster = route_score("B", travel_hours=10, low=100, severe=0.149)
    assert ids([slower, faster]) == ["B", "A"]


def test_should_not_tie_values_a_tenth_of_a_mile_or_more_apart():
    slower_with_less_severe = route_score("A", travel_hours=13, low=100, severe=0.05)
    faster_with_more_severe = route_score("B", travel_hours=10, low=100, severe=0.16)
    routes = [slower_with_less_severe, faster_with_more_severe]
    assert ids(routes) == ["A", "B"]
    assert comparison_for(routes, "B").criterion == "severe_miles"


def test_should_explain_a_route_by_the_criterion_that_ruled_it_out_against_the_leader():
    no_severe = route_score("A", travel_hours=12, low=100, severe=0.0)
    within_tolerance = route_score("B", travel_hours=11, low=100, severe=0.09)
    past_tolerance_of_the_leader = route_score("C", travel_hours=8, low=100, severe=0.12)
    ranking, comparisons = recommend([no_severe, within_tolerance, past_tolerance_of_the_leader])
    assert [ranked.route_id for ranked in ranking] == ["B", "A", "C"]
    by_route = {comparison.route_id: comparison for comparison in comparisons}
    assert by_route["A"].criterion == "travel_time"
    assert (by_route["C"].criterion, by_route["C"].leader_id, by_route["C"].leader_value) == ("severe_miles", "A", 0)
    assert by_route["C"].value == pytest.approx(0.12)


def test_should_tie_travel_times_less_than_a_minute_apart():
    first = route_score("A", travel_hours=10, low=100)
    twenty_seconds_faster = route_score("B", travel_hours=10 - 20 / HOUR, low=100)
    assert ids([first, twenty_seconds_faster]) == ["A", "B"]
    tie = comparison_for([first, twenty_seconds_faster], "B")
    assert (tie.criterion, tie.leader_id) == ("tie", "A")


def test_should_weight_average_risk_by_distance():
    three_quarters_low_one_quarter_severe = route_score("A", low=75, severe=25)
    assert three_quarters_low_one_quarter_severe.average_risk == 0.75


def test_should_keep_the_provider_order_on_a_full_tie():
    route_a, route_b = route_score("A", low=100), route_score("B", low=100)
    assert ids([route_a, route_b]) == ["A", "B"]
    assert comparison_for([route_a, route_b], "B").criterion == "tie"


def test_should_list_comparisons_in_ranking_order():
    slowest = route_score("A", travel_hours=12, low=100)
    fastest = route_score("B", travel_hours=10, low=100)
    middle = route_score("C", travel_hours=11, low=100)
    ranking, comparisons = recommend([slowest, fastest, middle])
    assert [ranked.route_id for ranked in ranking] == ["B", "C", "A"]
    assert [comparison.route_id for comparison in comparisons] == ["C", "A"]


def test_should_return_no_ranking_and_no_comparisons_for_no_routes():
    assert recommend([]) == ([], [])
