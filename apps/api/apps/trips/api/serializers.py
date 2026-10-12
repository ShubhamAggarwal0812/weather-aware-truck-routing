"""Request validation and response shapes for the trips API.

Request serializers validate input. Response serializers describe the output for
the OpenAPI schema (and the TypeScript types generated from it); the presenters
build the actual dicts, and ``tests/api/test_contract.py`` checks they match.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rest_framework import serializers

from apps.trips.domain.risk import RiskLevel
from apps.trips.services.planning import Place, TripInput
from common.geo import haversine_m

MAX_LOAD_LB = 80_000
INTERVALS_MILES = (10, 25, 50)
MAX_DAYS_AHEAD = 7
DEPARTURE_GRACE = timedelta(minutes=30)

RISK_KEYS = [level.key for level in RiskLevel]
CONDITIONS = ["wind", "rain", "snow"]


# --- Requests ---------------------------------------------------------------


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")  # type: ignore[assignment]


def validate_departure(value: datetime) -> None:
    now = datetime.now(UTC)
    if value < now - DEPARTURE_GRACE:
        raise serializers.ValidationError("Departure can't be in the past.")
    if value > now + timedelta(days=MAX_DAYS_AHEAD):
        raise serializers.ValidationError(f"Departure must be within the next {MAX_DAYS_AHEAD} days.")


class PlanRequestSerializer(serializers.Serializer):
    origin = LocationSerializer()
    destination = LocationSerializer()
    departure = serializers.DateTimeField(validators=[validate_departure], help_text="ISO 8601 with offset.")
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB, help_text="Cargo weight.")
    interval_miles = serializers.ChoiceField(choices=INTERVALS_MILES, default=25)
    rest_breaks = serializers.BooleanField(default=True, help_text="Add FMCSA hours-of-service breaks to ETAs.")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        o, d = attrs["origin"], attrs["destination"]
        if haversine_m((o["lat"], o["lon"]), (d["lat"], d["lon"])) < 1_000:
            raise serializers.ValidationError({"destination": "Destination must differ from the origin."})
        return attrs

    def to_trip(self) -> TripInput:
        v = self.validated_data
        return TripInput(
            origin=Place(**v["origin"]),
            destination=Place(**v["destination"]),
            departure=v["departure"].astimezone(UTC),
            load_weight_lb=v["load_weight_lb"],
            interval_miles=int(v["interval_miles"]),
            rest_breaks=v["rest_breaks"],
        )


class LatLonField(serializers.ListField):
    child = serializers.FloatField()

    def __init__(self, **kwargs: Any):
        super().__init__(min_length=2, max_length=2, **kwargs)

    def to_internal_value(self, data: Any) -> list[Any]:
        lat, lon = point = super().to_internal_value(data)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise serializers.ValidationError("Coordinates out of range.")
        return point


class CorridorRequestSerializer(serializers.Serializer):
    lines = serializers.ListField(
        child=serializers.ListField(child=LatLonField(), min_length=2, max_length=3000),
        min_length=1,
        max_length=3,
        help_text="Each route's `corridor_line` from the plan, as [lat, lon] points.",
    )
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)


# --- Responses ----------------------------------------------------------------


def _numbers(**kwargs: Any) -> serializers.ListField:
    return serializers.ListField(child=serializers.FloatField(), **kwargs)


class BandSerializer(serializers.Serializer):
    level = serializers.ChoiceField(choices=RISK_KEYS)
    threshold = serializers.FloatField()
    inclusive = serializers.BooleanField()


class LoadRuleSerializer(serializers.Serializer):
    min_wind_mph = serializers.FloatField()
    max_wind_mph = serializers.FloatField()
    min_load_lb = serializers.FloatField()
    level = serializers.ChoiceField(choices=RISK_KEYS)
    description = serializers.CharField()


class RiskLevelSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=RISK_KEYS)
    label = serializers.CharField()  # type: ignore[assignment]  # DRF pops declared fields
    score = serializers.IntegerField()


class RiskRulesSerializer(serializers.Serializer):
    levels = RiskLevelSerializer(many=True)
    wind_mph = BandSerializer(many=True)
    rain_in_hr = BandSerializer(many=True)
    snow_in_hr = BandSerializer(many=True)
    load_rules = LoadRuleSerializer(many=True)


class ProviderSerializer(serializers.Serializer):
    name = serializers.CharField()
    truck_aware = serializers.BooleanField()


class ConfigSerializer(serializers.Serializer):
    routing_provider = serializers.CharField()
    truck_aware = serializers.BooleanField()
    rules = RiskRulesSerializer()


class ConditionsSerializer(serializers.Serializer):
    wind_mph = serializers.FloatField()
    gust_mph = serializers.FloatField()
    rain_in_hr = serializers.FloatField()
    snow_in_hr = serializers.FloatField()
    temp_f = serializers.IntegerField()


class FactorSerializer(serializers.Serializer):
    condition = serializers.ChoiceField(choices=CONDITIONS)
    level = serializers.ChoiceField(choices=RISK_KEYS)
    load_rule = serializers.CharField(allow_null=True)


class CheckpointSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    mile = serializers.FloatField()
    covers_mi = _numbers(min_length=2, max_length=2, help_text="[from, to]: the stretch this checkpoint scores.")
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    eta = serializers.DateTimeField()
    drive_time_s = serializers.IntegerField()
    level = serializers.ChoiceField(choices=RISK_KEYS)
    conditions = ConditionsSerializer()
    factors = FactorSerializer(many=True)
    drivers = serializers.ListField(child=serializers.ChoiceField(choices=CONDITIONS))


class SegmentSerializer(serializers.Serializer):
    checkpoint = serializers.IntegerField()
    level = serializers.ChoiceField(choices=RISK_KEYS)
    coordinates = serializers.ListField(child=_numbers(min_length=2, max_length=2), help_text="[lon, lat] points.")


class StopSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["break", "rest"])
    mile = serializers.FloatField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class MilesByLevelSerializer(serializers.Serializer):
    low = serializers.FloatField()
    moderate = serializers.FloatField()
    high = serializers.FloatField()
    severe = serializers.FloatField()
    no_travel = serializers.FloatField()


class RouteRiskSerializer(serializers.Serializer):
    miles_by_level = MilesByLevelSerializer()
    average = serializers.FloatField(help_text="Distance-weighted, Low = 0 to No Travel = 4.")
    max_level = serializers.ChoiceField(choices=RISK_KEYS)


class RoutePlanSerializer(serializers.Serializer):
    id = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    rank = serializers.IntegerField()
    recommended = serializers.BooleanField()
    distance_mi = serializers.FloatField()
    drive_time_s = serializers.IntegerField()
    travel_time_s = serializers.IntegerField(help_text="Wall-clock trip time including HOS stops.")
    arrival = serializers.DateTimeField()
    notes = serializers.ListField(child=serializers.CharField())
    risk = RouteRiskSerializer()
    checkpoints = CheckpointSerializer(many=True)
    segments = SegmentSerializer(many=True)
    stops = StopSerializer(many=True)
    positions = serializers.ListField(
        child=_numbers(min_length=3, max_length=3),
        help_text="Every 15 min from heatmap_start for 48 h: [lat, lon, status]; "
        "status 0 waiting, 1 driving, 2 break, 3 rest, 4 arrived.",
    )
    corridor_line = serializers.ListField(
        child=_numbers(min_length=2, max_length=2), help_text="Simplified route as [lat, lon]."
    )


class ComparisonSerializer(serializers.Serializer):
    route_id = serializers.CharField()
    criterion = serializers.ChoiceField(
        choices=["no_travel_miles", "severe_miles", "high_miles", "average_risk", "travel_time", "tie"]
    )
    recommended_value = serializers.FloatField()
    other_value = serializers.FloatField()


class RecommendationSerializer(serializers.Serializer):
    route_id = serializers.CharField()
    safe = serializers.BooleanField()
    headline = serializers.CharField()
    reasons = serializers.ListField(child=serializers.CharField())
    comparisons = ComparisonSerializer(many=True)


class PlanSerializer(serializers.Serializer):
    provider = ProviderSerializer()
    departure = serializers.DateTimeField()
    load_weight_lb = serializers.IntegerField()
    gross_weight_lb = serializers.IntegerField()
    interval_miles = serializers.IntegerField()
    rest_breaks = serializers.BooleanField()
    heatmap_start = serializers.DateTimeField()
    routes = RoutePlanSerializer(many=True)
    recommendation = RecommendationSerializer()
    rules = RiskRulesSerializer()


class CorridorSerializer(serializers.Serializer):
    step_deg = serializers.FloatField()
    rows = serializers.ListField(child=serializers.IntegerField(), help_text="Cell centre latitude = row * step_deg.")
    cols = serializers.ListField(child=serializers.IntegerField(), help_text="Cell centre longitude = col * step_deg.")
    times = serializers.ListField(child=serializers.DateTimeField())
    wind_mph = serializers.ListField(child=_numbers(), help_text="[hour][cell]")
    rain_in_hr = serializers.ListField(child=_numbers(), help_text="[hour][cell]")
    snow_in_hr = serializers.ListField(child=_numbers(), help_text="[hour][cell]")
    risk = serializers.ListField(
        child=serializers.ListField(child=serializers.IntegerField()), help_text="[hour][cell] risk score 0-4."
    )
