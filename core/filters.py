import django_filters

from .models import Pet


class PetFilter(django_filters.FilterSet):  # type: ignore[misc]
    # 'icontains' makes it case-insensitive and matches any part of the string
    name = django_filters.CharFilter(lookup_expr="icontains")
    breed = django_filters.CharFilter(lookup_expr="icontains")

    # Date range filtering for birth_date
    birth_date_after = django_filters.DateFilter(
        field_name="birth_date", lookup_expr="gte"
    )
    birth_date_before = django_filters.DateFilter(
        field_name="birth_date", lookup_expr="lte"
    )

    class Meta:
        model = Pet
        fields = {
            "species": ["exact"],
            "sex": ["exact"],
            "size": ["exact"],
            "status": ["exact"],
            "origin": ["exact"],
            "organization": ["exact"],
        }
