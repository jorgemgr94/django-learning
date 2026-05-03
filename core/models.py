from django.db import models


class PetSpecies(models.TextChoices):
    DOG = "dog", "Dog"
    CAT = "cat", "Cat"


class PetSex(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class PetSize(models.TextChoices):
    SMALL = "small", "Small"
    MEDIUM = "medium", "Medium"
    LARGE = "large", "Large"


class PetStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    AVAILABLE = "available", "Available"
    ADOPTED = "adopted", "Adopted"
    ARCHIVED = "archived", "Archived"


class PetOrigin(models.TextChoices):
    RESCUE = "rescue", "Rescue"
    OWNER_SURRENDER = "owner_surrender", "Owner Surrender"
    STRAY = "stray", "Stray"


class Organization(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Pet(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="pets",
    )
    name = models.CharField(max_length=100)
    species = models.CharField(max_length=20, choices=PetSpecies.choices)
    breed = models.CharField(max_length=100, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=PetSex.choices)
    size = models.CharField(max_length=10, choices=PetSize.choices)
    color = models.CharField(max_length=50, blank=True, default="")
    description = models.TextField(blank=True, default="")
    temperament = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=PetStatus.choices,
        default=PetStatus.SUBMITTED,
    )
    origin = models.CharField(
        max_length=20,
        choices=PetOrigin.choices,
        default=PetOrigin.RESCUE,
    )
    image = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.species})"
