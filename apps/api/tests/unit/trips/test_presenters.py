from apps.trips.domain.recommend import recommend
from apps.trips.services.presenters import _reason
from tests.fakes import route_score

SECONDS_PER_HOUR = 3600


def recommended_and_reasons(scores):
    ranking, comparisons = recommend(scores)
    recommended = ranking[0].route_id
    return recommended, [_reason(recommended, comparison) for comparison in comparisons]


def test_should_explain_a_route_against_the_recommended_one_when_that_route_ruled_it_out():
    recommended, reasons = recommended_and_reasons(
        [route_score("A", travel_hours=11, low=100), route_score("B", travel_hours=10, low=100)]
    )
    assert (recommended, reasons) == ("B", ["Same weather risk as Route A and 1 h 0 min faster."])


def test_should_explain_a_slower_route_against_the_one_that_set_the_pace_not_the_recommended_one():
    pace_setter = route_score("B", travel_hours=1, low=100)
    within_a_minute_and_first_in_provider_order = route_score("A", travel_hours=3659 / SECONDS_PER_HOUR, low=100)
    a_minute_behind_the_pace_setter = route_score("C", travel_hours=3660 / SECONDS_PER_HOUR, low=100)
    recommended, reasons = recommended_and_reasons(
        [within_a_minute_and_first_in_provider_order, pace_setter, a_minute_behind_the_pace_setter]
    )
    assert recommended == "A"
    assert reasons == [
        "Ties with Route B on every criterion; Route A comes first in the provider's order.",
        "Route C has the same weather risk as Route B but takes 1 min longer.",
    ]


def test_should_show_average_risks_that_differ_at_the_precision_shown():
    average_risk_0_509 = route_score("A", travel_hours=9, low=49.1, moderate=50.9)
    average_risk_0_500 = route_score("B", travel_hours=10, low=50, moderate=50)
    average_risk_0_511 = route_score("C", travel_hours=8, low=48.9, moderate=51.1)
    recommended, reasons = recommended_and_reasons([average_risk_0_509, average_risk_0_500, average_risk_0_511])
    assert recommended == "A"
    assert reasons[-1] == "Route C has a higher average risk than Route B (0.51 vs 0.50)."


def test_should_name_the_route_with_fewer_severe_miles_when_it_is_not_the_recommended_one():
    recommended, reasons = recommended_and_reasons(
        [
            route_score("A", travel_hours=10, low=100, severe=0.09),
            route_score("B", travel_hours=10.5, low=100, severe=0),
            route_score("C", travel_hours=9.45, low=100, severe=0.105),
        ]
    )
    assert recommended == "A"
    assert reasons == [
        "Same weather risk as Route B and 30 min faster.",
        "Route C has more Severe miles than Route B (0.1 vs 0 mi).",
    ]


def test_should_not_print_a_sliver_of_no_travel_as_zero():
    recommended, reasons = recommended_and_reasons(
        [route_score("A", travel_hours=8, low=100, no_travel=0.003), route_score("B", travel_hours=9, low=100)]
    )
    assert (recommended, reasons) == ("B", ["Fewer No Travel miles than Route A (0 vs under 0.01 mi)."])


def test_should_explain_fewer_high_miles_against_the_recommended_route():
    recommended, reasons = recommended_and_reasons(
        [route_score("A", travel_hours=8, low=90, high=10), route_score("B", travel_hours=12, low=100)]
    )
    assert (recommended, reasons) == ("B", ["Same Severe mileage as Route A, fewer High miles (0 vs 10 mi)."])


def test_should_explain_a_higher_average_risk_against_the_recommended_route():
    recommended, reasons = recommended_and_reasons(
        [route_score("A", travel_hours=8, low=50, moderate=50), route_score("B", travel_hours=9, low=100)]
    )
    assert (recommended, reasons) == (
        "B",
        ["Same Severe and High mileage as Route A, lower average risk (0.00 vs 0.50)."],
    )


def test_should_name_the_route_with_fewer_high_miles_when_it_is_not_the_recommended_one():
    recommended, reasons = recommended_and_reasons(
        [
            route_score("A", travel_hours=10, low=100, high=0.09),
            route_score("B", travel_hours=11, low=100),
            route_score("C", travel_hours=9, low=100, high=0.2),
        ]
    )
    assert recommended == "A"
    assert reasons[-1] == "Route C has more High miles than Route B (0.2 vs 0 mi)."
