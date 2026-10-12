from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rest_framework import serializers

from trips.domain.geo import haversine_m
from trips.services.planner import Place, TripInput

MAX_LOAD_LB = 80_000
INTERVALS_MILES = (10, 25, 50)
MAX_DAYS_AHEAD = 7
DEPARTURE_GRACE = timedelta(minutes=30)


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


def validate_departure(value: datetime) -> datetime:
    now = datetime.now(UTC)
    if value < now - DEPARTURE_GRACE:
        raise serializers.ValidationError("Departure can't be in the past.")
    if value > now + timedelta(days=MAX_DAYS_AHEAD):
        raise serializers.ValidationError(f"Departure must be within the next {MAX_DAYS_AHEAD} days.")
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=INTERVALS_MILES, default=25)
    rest_breaks = serializers.BooleanField(default=True)

    def validate(self, attrs: dict) -> dict:
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

    def __init__(self, **kwargs):
        super().__init__(min_length=2, max_length=2, **kwargs)

    def to_internal_value(self, data):
        lat, lon = super().to_internal_value(data)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise serializers.ValidationError("Coordinates out of range.")
        return (lat, lon)


class CorridorRequestSerializer(serializers.Serializer):
    lines = serializers.ListField(
        child=serializers.ListField(child=LatLonField(), min_length=2, max_length=3000),
        min_length=1,
        max_length=3,
    )
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=120, trim_whitespace=True)
