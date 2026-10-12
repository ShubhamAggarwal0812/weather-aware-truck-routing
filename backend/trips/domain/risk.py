"""Weather risk classification, straight from the assessment's risk and load tables.

Boundary handling. The spec's ranges share their end points (rain "0.10-0.25"
and "0.25-0.50"), so each band here starts at its lower bound:

    Wind  Low <25 | Moderate 25-<35 | High 35-<45 | Severe 45-<55 | No Travel >=55 mph
    Rain  Low <0.10 | Moderate 0.10-<0.25 | High 0.25-<0.50 | Severe 0.50-1.00 | No Travel >1.00 in/hr
    Snow  Low <0.5  | Moderate 0.5-<1.0   | High 1.0-<2.0   | Severe 2.0-3.0   | No Travel >3.0 in/hr

No Travel is "≥55" for wind but strictly ">1.00" / ">3.0" for rain and snow, as
the table says, so 1.00 in/hr of rain is still Severe.

A checkpoint's level is the worst of its three conditions after the load rules
have been applied to wind.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Band:
    """A level that starts at ``threshold``. ``inclusive`` decides the boundary value."""

    level: RiskLevel
    threshold: float
    inclusive: bool = True

    def reached_by(self, value: float) -> bool:
        return value >= self.threshold if self.inclusive else value > self.threshold


WIND_BANDS_MPH = (
    Band(RiskLevel.MODERATE, 25),
    Band(RiskLevel.HIGH, 35),
    Band(RiskLevel.SEVERE, 45),
    Band(RiskLevel.NO_TRAVEL, 55),
)
RAIN_BANDS_IN_HR = (
    Band(RiskLevel.MODERATE, 0.10),
    Band(RiskLevel.HIGH, 0.25),
    Band(RiskLevel.SEVERE, 0.50),
    Band(RiskLevel.NO_TRAVEL, 1.00, inclusive=False),
)
SNOW_BANDS_IN_HR = (
    Band(RiskLevel.MODERATE, 0.5),
    Band(RiskLevel.HIGH, 1.0),
    Band(RiskLevel.SEVERE, 2.0),
    Band(RiskLevel.NO_TRAVEL, 3.0, inclusive=False),
)


@dataclass(frozen=True)
class LoadRule:
    """Wind in [min_wind, max_wind) with load above ``min_load_lb`` escalates to ``level``."""

    min_wind_mph: float
    max_wind_mph: float
    min_load_lb: float
    level: RiskLevel
    description: str

    def applies(self, wind_mph: float, load_lb: float) -> bool:
        return self.min_wind_mph <= wind_mph < self.max_wind_mph and load_lb > self.min_load_lb


# ">=55 mph -> No Travel for any load" is already the top wind band.
LOAD_RULES = (
    LoadRule(45, 55, 30_000, RiskLevel.NO_TRAVEL, "45-54 mph wind with a load over 30,000 lb"),
    LoadRule(35, 45, 40_000, RiskLevel.SEVERE, "35-44 mph wind with a load over 40,000 lb"),
)


def classify(value: float, bands: tuple[Band, ...]) -> RiskLevel:
    level = RiskLevel.LOW
    for band in bands:
        if band.reached_by(value):
            level = band.level
    return level


def wind_level(wind_mph: float, load_lb: float) -> tuple[RiskLevel, LoadRule | None]:
    """Wind level after the load rules. Returns the load rule that raised it, if any."""
    base = classify(wind_mph, WIND_BANDS_MPH)
    for rule in LOAD_RULES:
        if rule.applies(wind_mph, load_lb) and rule.level > base:
            return rule.level, rule
    return base, None


@dataclass(frozen=True)
class Conditions:
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float


@dataclass(frozen=True)
class Factor:
    condition: str  # "wind" | "rain" | "snow"
    value: float
    level: RiskLevel
    load_rule: str | None = None


@dataclass(frozen=True)
class Assessment:
    level: RiskLevel
    factors: tuple[Factor, ...]

    @property
    def drivers(self) -> tuple[Factor, ...]:
        """The conditions responsible for the overall level (empty when Low)."""
        if self.level == RiskLevel.LOW:
            return ()
        return tuple(f for f in self.factors if f.level == self.level)


def assess(conditions: Conditions, load_lb: float) -> Assessment:
    wind, rule = wind_level(conditions.wind_mph, load_lb)
    factors = (
        Factor("wind", conditions.wind_mph, wind, rule.description if rule else None),
        Factor("rain", conditions.rain_in_hr, classify(conditions.rain_in_hr, RAIN_BANDS_IN_HR)),
        Factor("snow", conditions.snow_in_hr, classify(conditions.snow_in_hr, SNOW_BANDS_IN_HR)),
    )
    return Assessment(max(f.level for f in factors), factors)


def rules_table() -> dict:
    """The thresholds in a JSON-friendly shape, so the UI legend never drifts from the logic."""

    def bands(items: tuple[Band, ...]) -> list[dict]:
        return [{"level": b.level.key, "threshold": b.threshold, "inclusive": b.inclusive} for b in items]

    return {
        "levels": [{"key": lvl.key, "label": lvl.label, "score": int(lvl)} for lvl in RiskLevel],
        "wind_mph": bands(WIND_BANDS_MPH),
        "rain_in_hr": bands(RAIN_BANDS_IN_HR),
        "snow_in_hr": bands(SNOW_BANDS_IN_HR),
        "load_rules": [
            {
                "min_wind_mph": r.min_wind_mph,
                "max_wind_mph": r.max_wind_mph,
                "min_load_lb": r.min_load_lb,
                "level": r.level.key,
                "description": r.description,
            }
            for r in LOAD_RULES
        ],
    }
