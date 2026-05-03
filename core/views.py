from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from pydantic import ValidationError as PydanticValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from . import services
from .models import Organization, Pet, PetStatus
from .permissions import IsOwnerOrganizationOrReadOnly
from .schemas import BulkStatusUpdateInput
from .serializers import OrganizationSerializer, PetSerializer


class OrganizationViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def get_permissions(self) -> list[Any]:
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated(), IsOwnerOrganizationOrReadOnly()]


class PetViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    serializer_class = PetSerializer
    search_fields = ["name", "breed", "description"]
    ordering_fields = ["name", "created_at", "birth_date"]
    ordering = ["-name"]

    queryset = Pet.objects.all()

    def get_permissions(self) -> list[Any]:
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated(), IsOwnerOrganizationOrReadOnly()]

    @action(detail=True, methods=["post"], url_path="change-status")
    def change_status(self, request: Request, pk: str | None = None) -> Response:
        pet: Pet = self.get_object()
        new_status = request.data.get("status")

        if not new_status:
            return Response(
                {"error": "Field 'status' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pet_status = PetStatus(new_status)
        except ValueError:
            return Response(
                {"error": f"Invalid status '{new_status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated_pet = services.change_status(
                pet=pet,
                new_status=pet_status,
                changed_by_user_id=request.user.id,
            )
        except DjangoValidationError as e:
            return Response(
                {"error": e.message},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(self.get_serializer(updated_pet).data)

    @action(detail=False, methods=["post"], url_path="bulk-status")
    def bulk_status_update(self, request: Request) -> Response:
        try:
            payload = BulkStatusUpdateInput(**request.data)
        except PydanticValidationError as e:
            return Response(
                {"errors": e.errors()},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        updated = services.bulk_update_status(
            pet_ids=payload.pet_ids,
            new_status=PetStatus(payload.new_status),
        )
        return Response({"updated": updated})
