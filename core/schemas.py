from dataclasses import dataclass
from datetime import date
from typing import TypedDict


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
