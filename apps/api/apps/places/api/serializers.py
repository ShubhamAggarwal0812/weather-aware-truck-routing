from rest_framework import serializers


class PlaceQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=120, trim_whitespace=True)


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField()  # type: ignore[assignment]  # DRF pops declared fields
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class PlaceSearchResponseSerializer(serializers.Serializer):
    results = PlaceSerializer(many=True)
