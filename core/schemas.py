from dataclasses import dataclass
from datetime import date
from typing import Literal, TypedDict

from pydantic import BaseModel, field_validator, model_validator


class PetSummary(TypedDict):
    """Structure to pass summarized data internally without using the ORM."""

    id: int
    name: str
    species: str
    status: str
    organization_name: str


class PaginationContext(TypedDict):
    """Structured pagination context to pass between layers."""

    page: int
    page_size: int
    total: int


@dataclass
class PetSearchFilters:
    """
    Typed search filters.
    Allows passing data from the HTTP layer (view) to the service layer
    without mixing QueryParams logic with business logic.
    """

    species: str | None = None
    size: str | None = None
    status: str | None = None
    organization_id: int | None = None
    birth_date_after: date | None = None
    birth_date_before: date | None = None

    def has_filters(self) -> bool:
        """Check if the user applied at least one filter."""
        return any([self.species, self.size, self.status, self.organization_id])


@dataclass(frozen=True)
class PetStatusTransition:
    """
    Represents a valid state transition immutably.
    """

    from_status: str
    to_status: str
    reason: str = ""

    def __str__(self) -> str:
        return f"{self.from_status} → {self.to_status}"


# == Pydantic ==============================
class PetStatusChangedPayload(BaseModel):
    pet_id: int
    old_status: str
    new_status: str
    changed_by_user_id: int | None = None

    @field_validator("new_status")
    @classmethod
    def validate_new_status(cls, v: str) -> str:
        valid = {"submitted", "available", "adopted", "archived"}
        if v not in valid:
            raise ValueError(f"Invalid status '{v}'. Must be one of {valid}")
        return v


class BreedInfo(BaseModel):
    name: str
    origin: str | None = None
    temperament: str | None = None
    life_span: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Breed name cannot be empty")
        return v.strip()


class BulkStatusUpdateInput(BaseModel):
    pet_ids: list[int]
    new_status: Literal["available", "archived"]
    reason: str = ""

    @model_validator(mode="after")
    def validate_pet_ids(self) -> "BulkStatusUpdateInput":
        if not self.pet_ids:
            raise ValueError("pet_ids cannot be empty")
        if len(self.pet_ids) > 100:
            raise ValueError("Cannot update more than 100 pets at once")
        return self
