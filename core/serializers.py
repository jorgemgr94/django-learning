from typing import Any

from rest_framework import serializers

from .models import Organization, Pet


class OrganizationSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    class Meta:
        model = Organization
        fields = ["id", "name", "email", "created_at"]
        read_only_fields = ["id", "created_at"]


class PetSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    class Meta:
        model = Pet
        fields = [
            "id",
            "organization",
            "name",
            "species",
            "breed",
            "birth_date",
            "sex",
            "size",
            "color",
            "description",
            "temperament",
            "status",
            "origin",
            "image",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # -------------------------------------------------------------------
    # Field-level validations
    # -------------------------------------------------------------------
    def validate_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Name cannot be blank.")
        return value.strip()

    # -------------------------------------------------------------------
    # Cross-field (object-level) validation
    # validate() receives all individually validated fields.
    # -------------------------------------------------------------------
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("status") == "adopted" and not attrs.get("description", ""):
            raise serializers.ValidationError(
                {"description": "Adopted pets must have a description."}
            )
        return attrs
