"""Route ranking, in the order the assessment gives:

    1. fewest Severe miles  2. fewest High miles  3. lowest average risk  4. shortest travel time

No Travel isn't in that list, but a route with any No Travel miles can't be
safer than one without, so No Travel miles are compared first.

Miles are compared at 0.1 mi and average risk at 0.01. Below that the difference
is sampling noise, and the next criterion (finally travel time) decides.
"""

from __future__ import annotations

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

    def sort_key(self) -> tuple[float, float, float, float, float]:
        return (
            round(self.miles(RiskLevel.NO_TRAVEL), 1),
            round(self.miles(RiskLevel.SEVERE), 1),
            round(self.miles(RiskLevel.HIGH), 1),
            round(self.average_risk, 2),
            self.travel_s,
        )


@dataclass(frozen=True)
class Comparison:
    """Why the recommended route beats one other route: the first criterion that differs."""

    route_id: str
    criterion: str  # "no_travel_miles" | "severe_miles" | "high_miles" | "average_risk" | "travel_time" | "tie"
    recommended_value: float
    other_value: float


CRITERIA = ("no_travel_miles", "severe_miles", "high_miles", "average_risk", "travel_time")


def rank(scores: list[RouteScore]) -> list[RouteScore]:
    """Best first. Python's sort is stable, so exact ties keep the provider's order."""
    return sorted(scores, key=RouteScore.sort_key)


def compare(best: RouteScore, other: RouteScore) -> Comparison:
    for criterion, a, b in zip(CRITERIA, best.sort_key(), other.sort_key()):
        if a != b:
            return Comparison(other.route_id, criterion, a, b)
    return Comparison(other.route_id, "tie", 0.0, 0.0)
