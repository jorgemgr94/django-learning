from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Pet, PetStatus
from .schemas import PetStatusChangedPayload

# Valid state machine transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    PetStatus.SUBMITTED: {PetStatus.AVAILABLE, PetStatus.ARCHIVED},
    PetStatus.AVAILABLE: {PetStatus.ADOPTED, PetStatus.ARCHIVED},
    PetStatus.ADOPTED: {PetStatus.AVAILABLE},
    PetStatus.ARCHIVED: set(),  # final state
}


def change_status(
    pet: Pet,
    new_status: PetStatus,
    changed_by_user_id: int | None = None,
) -> Pet:
    """
    Transition a pet's status applying state machine rules.
    Raises ValidationError if the transition is not allowed.
    """
    allowed = VALID_TRANSITIONS.get(pet.status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"Cannot transition '{pet.status}' → '{new_status}'. "
            f"Allowed: {allowed or 'none (final state)'}"
        )

    old_status = pet.status
    pet.status = new_status
    pet.save(update_fields=["status", "updated_at"])

    # Fire async notification via Celery
    from .tasks import notify_status_change  # local import → avoids circular

    payload = PetStatusChangedPayload(
        pet_id=pet.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_user_id=changed_by_user_id,
    )
    notify_status_change.delay(payload.model_dump())

    return pet


@transaction.atomic
def bulk_update_status(pet_ids: list[int], new_status: PetStatus) -> int:
    """
    Update multiple pets in a single transaction.
    """
    pets = list(Pet.objects.filter(id__in=pet_ids).select_for_update())

    if len(pets) != len(pet_ids):
        raise ValidationError("Some pet IDs were not found.")

    valid_pets: list[Pet] = []
    for pet in pets:
        allowed = VALID_TRANSITIONS.get(pet.status, set())
        if new_status in allowed:
            pet.status = new_status
            valid_pets.append(pet)

    if valid_pets:
        Pet.objects.bulk_update(valid_pets, ["status", "updated_at"])

    return len(valid_pets)
