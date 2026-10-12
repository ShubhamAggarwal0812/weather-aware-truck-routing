from typing import Any

from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """Shape of every error response (documented in the OpenAPI schema)."""

    error = serializers.CharField()

    def get_fields(self) -> dict[str, Any]:
        # "fields" can't be a class attribute: it would shadow Serializer.fields for type checkers.
        fields = super().get_fields()
        fields["fields"] = serializers.DictField(required=False, help_text="Per-field validation messages.")
        return fields
