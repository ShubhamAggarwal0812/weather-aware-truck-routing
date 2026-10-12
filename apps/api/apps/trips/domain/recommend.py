"""Route ranking, in the order the assessment gives:

    1. fewest Severe miles  2. fewest High miles  3. lowest average risk  4. shortest travel time

No Travel isn't in that list, but a route with any No Travel miles can't be
safer than one without, so No Travel miles are compared first.

Miles are compared at 0.1 mi and average risk at 0.01. Below that the difference
is sampling noise, and the next criterion (finally travel time) decides.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from common.geo import METERS_PER_MILE

from .risk import RiskLevel


@dataclass
class RouteScore:
    route_id: str
    meters_by_level: dict[RiskLevel, float]
    travel_s: float  # wall-clock trip time, including any rest breaks
    distance_m: float = field(init=False)
    average_risk: float = field(init=False)

    def __post_init__(self) -> None:
        self.distance_m = sum(self.meters_by_level.values())
        weighted = sum(int(level) * m for level, m in self.meters_by_level.items())
        self.average_risk = weighted / self.distance_m if self.distance_m else 0.0

    def miles(self, level: RiskLevel) -> float:
        return self.meters_by_level.get(level, 0.0) / METERS_PER_MILE


@dataclass(frozen=True)
class Comparison:
    route_id: str
    criterion: str  # "no_travel_miles" | "severe_miles" | "high_miles" | "average_risk" | "travel_time" | "tie"
    recommended_value: float
    other_value: float


@dataclass(frozen=True)
class _Criterion:
    name: str
    value: Callable[[RouteScore], float]
    tolerance: float
    decimal_places: int


CRITERIA = (
    _Criterion("no_travel_miles", lambda score: score.miles(RiskLevel.NO_TRAVEL), 0.1, 2),
    _Criterion("severe_miles", lambda score: score.miles(RiskLevel.SEVERE), 0.1, 2),
    _Criterion("high_miles", lambda score: score.miles(RiskLevel.HIGH), 0.1, 2),
    _Criterion("average_risk", lambda score: score.average_risk, 0.01, 3),
    _Criterion("travel_time", lambda score: score.travel_s, 60.0, 0),
)


def _select(scores: list[RouteScore]) -> tuple[RouteScore, dict[str, Comparison]]:
    remaining = list(scores)
    ruled_out: dict[str, tuple[_Criterion, RouteScore]] = {}
    for criterion in CRITERIA:
        values = {score.route_id: criterion.value(score) for score in remaining}
        leading_value = min(values.values())
        # Measured from the leader, not by rounding into buckets, so values a hair apart can't land in different
        # buckets; and any No Travel at all loses to none, because no amount of it is sampling noise.
        if criterion.name == "no_travel_miles" and leading_value == 0:
            kept = {route_id for route_id, value in values.items() if value == 0}
        else:
            kept = {route_id for route_id, value in values.items() if value < leading_value + criterion.tolerance}
        ruled_out.update((score.route_id, (criterion, score)) for score in remaining if score.route_id not in kept)
        remaining = [score for score in remaining if score.route_id in kept]
    # The scores arrive in the provider's order, so a full tie goes to the provider's first route.
    best = remaining[0]
    comparisons = {
        route_id: Comparison(
            route_id,
            criterion.name,
            round(criterion.value(best), criterion.decimal_places),
            round(criterion.value(other), criterion.decimal_places),
        )
        for route_id, (criterion, other) in ruled_out.items()
    }
    for tied in remaining[1:]:
        comparisons[tied.route_id] = Comparison(tied.route_id, "tie", 0.0, 0.0)
    return best, comparisons


def recommend(scores: list[RouteScore]) -> tuple[list[RouteScore], list[Comparison]]:
    if not scores:
        return [], []
    best, comparisons = _select(scores)
    ranking, remaining = [best], [score for score in scores if score is not best]
    while remaining:
        next_best, _ = _select(remaining)
        ranking.append(next_best)
        remaining.remove(next_best)
    return ranking, [comparisons[score.route_id] for score in ranking[1:]]
