# ConectaPelu2 — Findings & Best Practices Audit (Phases 0–10)

> **Goal:** A pragmatic review of the current state of phases 0–10 against
> the original learning plan and Django/DRF production-grade best practices.
> Each finding has a **severity**, the **observed behavior**, the **risk**,
> and a **concrete fix** so it can be turned into a Linear/Jira ticket.

**Severity legend**

| Tag | Meaning |
|-----|---------|
| 🔴 Critical | Causes runtime failures or silent data loss. Fix before merging more features. |
| 🟠 High | Real production risk (security, consistency, scalability) — fix in a near sprint. |
| 🟡 Medium | Hurts maintainability, DX or correctness in edge cases. Schedule it. |
| 🟢 Low / Nit | Style or polish. Fix when nearby code is touched. |
| 💡 Insight | Intentional divergence from the plan worth documenting. |

---

## Summary by phase

| Fase | Status | Notes |
|------|--------|-------|
| 0 — Setup (uv + Docker) | ✅ Complete | All audit findings resolved (see git history). |
| 1 — Models | ✅ Complete with divergence | `Profile` model added, `PetSpecies` reduced to `dog`/`cat`. |
| 2 — `dataclass` / `TypedDict` | ⚠️ Defined, not wired | All four helper types are dead code. |
| 3 — Serializers | ⚠️ Functional but reduced | Lost nested-org-read, `*_display` fields, `organization_id` write split. |
| 4 — Pydantic | ✅ Complete | `BreedInfo` is dead code. |
| 5 — Service Layer | ✅ Complete with divergence | Module functions vs class; `bulk_update` skips notifications. |
| 6 — ViewSets / Routers | ✅ Complete with divergence | No `available` action. URL prefix is `/api/v1/`. |
| 7 — JWT | ⚠️ Configured but inconsistent | Token rotation enabled without blacklist app installed. |
| 8 — Permissions | ✅ Improved over plan | Multi-org membership via `Profile`, but no auto-creation hook. |
| 9 — Filters / search / pagination | ✅ Complete | `breed` icontains added (nice extra). |
| 10 — Performance | ✅ Complete | `select_related` + `Count` annotation in place. |

---

## Phase 1 — Models

### F-1.1 💡 `Profile` model added (not in plan)
- **File:** `core/models.py`
- **Observed:** A `Profile` with `OneToOneField(User)` and M2M to `Organization`. This is required by the new `IsOwnerOrganizationOrReadOnly` (see F-8.1).
- **Insight:** Sensible upgrade — supports a user belonging to multiple shelters. Document the rationale in the README so future readers don't think it's unused.

### F-1.2 🟠 No auto-creation of `Profile` for new users
- **File:** `core/models.py` (no signal / no `post_save`)
- **Risk:** `createsuperuser` produces a `User` without a `Profile`. Any write attempt then hits `IsOwnerOrganizationOrReadOnly`, which requires `request.user.profile` and silently denies permission.
- **Fix (recommended):** Use a signal:

```python
# core/signals.py
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Profile

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
```

Wire it in `core/apps.py`:

```python
class CoreConfig(AppConfig):
    name = "core"
    def ready(self) -> None:
        from . import signals  # noqa: F401
```

### F-1.5 🟡 No DB indexes on hot filter columns
- **Files:** `core/models.py`
- **Observed:** `Pet.status`, `Pet.species`, `Pet.organization_id` are common filter fields with no `db_index=True` and no `Meta.indexes`.
- **Risk:** As the dataset grows, the `?species=dog&status=available` filter does a sequential scan.
- **Fix:**

```python
class Pet(models.Model):
    ...
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["species", "status"]),  # composite for common combo
            models.Index(fields=["organization", "status"]),
        ]
```

### F-1.6 🟡 No `verbose_name`, no `Meta.verbose_name_plural`
- **Risk:** Admin and DRF browsable API render "Pets" as default plural — works for English, breaks for the Spanish-speaking domain ("Mascotas"). Define them now, before the data model freezes.

---

## Phase 2 — Internal types (`dataclass` / `TypedDict`)

### F-2.1 🟡 All Phase-2 helpers are unused
- **File:** `core/schemas.py`
- **Observed:** `PetSummary`, `PaginationContext`, `PetSearchFilters`, `PetStatusTransition` are defined but never imported.
- **Risk:** Dead code rots — by the time you need them, they'll be out of sync with the model.
- **Fix:** Either:
  1. Wire `PetSearchFilters` into the service layer (e.g., `services.search_pets(filters: PetSearchFilters)`) and use it from the `@action`s, or
  2. Move the helpers under `if TYPE_CHECKING:` / delete them and document them in this learning plan only.

### F-2.2 🟢 Mixing concerns in `core/schemas.py`
- **Observed:** The same file holds `TypedDict`, `dataclass`, and Pydantic models.
- **Insight:** Acceptable for a small project, but at a certain size split into:
  - `core/types.py` → `TypedDict` and `dataclass`
  - `core/schemas.py` → Pydantic only (matches DRF conventions)

---

## Phase 3 — Serializers

### F-3.1 🟡 `PetSerializer` lost the nested-read / id-write split
- **File:** `core/serializers.py`
- **Observed:** `organization` is a single `PrimaryKeyRelatedField` (default behavior).
- **Plan goal:** GETs return the org **object**, POST/PATCH accept just the **id**.
- **Risk:** Frontend has to make a second request per pet (or denormalize itself) to render "Pet name — Shelter name".
- **Fix:**

```python
class OrganizationMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name"]


class PetSerializer(serializers.ModelSerializer):
    organization = OrganizationMinimalSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        source="organization",
        write_only=True,
    )
    species_display = serializers.CharField(
        source="get_species_display", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    ...
```

> Note: `source="get_FOO_display"` is more concise than `SerializerMethodField`. Use the method approach only when display logic is not a simple `get_X_display()`.

### F-3.2 🟡 Cross-field validation references a magic string
- **File:** `core/serializers.py:53`
- **Observed:** `if attrs.get("status") == "adopted"`.
- **Risk:** Renaming the choice value silently breaks validation.
- **Fix:** `from .models import PetStatus` and compare to `PetStatus.ADOPTED`.

### F-3.3 🟢 No serializer for the `change-status` action
- **Plan:** Each `@action` should ideally have its own serializer for OpenAPI generation later (`drf-spectacular`).
- **Fix:** Add a `PetStatusChangeSerializer` (single field `status`) to:
  - normalize `400` errors into DRF format,
  - get auto-documented endpoints when you add Spectacular (Phase 17 in the roadmap).

---

## Phase 4 — Pydantic

### F-4.1 🟡 Hardcoded valid status set in `PetStatusChangedPayload`
- **File:** `core/schemas.py:70` — `valid = {"submitted", "available", "adopted", "archived"}`
- **Risk:** Two sources of truth (`PetStatus.values` vs the literal set). Adding a new status drifts.
- **Fix:**

```python
from .models import PetStatus

@field_validator("new_status")
@classmethod
def validate_new_status(cls, v: str) -> str:
    if v not in PetStatus.values:
        raise ValueError(f"Invalid status '{v}'. Must be one of {PetStatus.values}")
    return v
```

### F-4.2 🟡 `BreedInfo` is dead code
- **File:** `core/schemas.py`
- **Insight:** Either delete it or use it in a real external-API integration in Phase 13 (Celery) or Phase 20 (async views). Flag with `# usage: <where>` while waiting.

---

## Phase 5 — Service Layer

### F-5.1 💡 Module-level functions instead of `PetService` class
- **Observed:** `services.change_status(...)`, `services.bulk_update_status(...)` are plain functions; the plan used a class with `@staticmethod` methods.
- **Insight:** This is **more Pythonic** for a stateless service. Keep the current style; the class form added zero behavior. Just ensure tests do `from core import services` so each function stays mockable.

### F-5.2 🟠 Celery task fires before the DB transaction commits
- **File:** `core/services.py:45`
- **Observed:** `notify_status_change.delay(...)` is called immediately after `pet.save(...)`.
- **Risk:** When `change_status` is called inside an outer atomic block (e.g., from a view wrapped in `ATOMIC_REQUESTS`, or from `bulk_update_status`), the worker can pick the task **before** the DB commit lands. The worker queries Postgres for `pet_id=…` and finds the **old** state — a real-world race condition.
- **Fix:** Use `transaction.on_commit`:

```python
from django.db import transaction

transaction.on_commit(
    lambda: notify_status_change.delay(payload.model_dump())
)
```

### F-5.3 🟠 `bulk_update_status` silently diverges from `change_status`
- **File:** `core/services.py:51-70`
- **Observed:**
  1. It uses `Pet.objects.bulk_update(...)` — does **not** call `save()`, so `auto_now=True` on `updated_at` is **not** triggered. The `["status", "updated_at"]` in `bulk_update` only updates the column to whatever Python value `pet.updated_at` currently holds (i.e., the value loaded from the DB, unchanged).
  2. It does **not** fire `notify_status_change` per pet.
  3. Invalid transitions are silently skipped — caller can't tell which IDs failed.
- **Risk:** Inconsistent business rules between single and bulk paths. `updated_at` lies.
- **Fix:**

```python
from django.utils import timezone
from django.db.models.fields.json import JSONField  # not needed, just for clarity

@transaction.atomic
def bulk_update_status(
    pet_ids: list[int],
    new_status: PetStatus,
    changed_by_user_id: int | None = None,
) -> dict[str, list[int]]:
    pets = list(
        Pet.objects.filter(id__in=pet_ids).select_for_update()
    )
    found_ids = {p.id for p in pets}
    not_found = [pid for pid in pet_ids if pid not in found_ids]

    updated, skipped = [], []
    now = timezone.now()
    for pet in pets:
        allowed = VALID_TRANSITIONS.get(pet.status, set())
        if new_status not in allowed:
            skipped.append(pet.id)
            continue
        pet.status = new_status
        pet.updated_at = now
        updated.append(pet)

    Pet.objects.bulk_update(updated, ["status", "updated_at"])

    for pet in updated:
        payload = PetStatusChangedPayload(
            pet_id=pet.id, old_status=..., new_status=new_status,
            changed_by_user_id=changed_by_user_id,
        )
        transaction.on_commit(
            lambda p=payload: notify_status_change.delay(p.model_dump())
        )

    return {"updated": [p.id for p in updated], "skipped": skipped, "not_found": not_found}
```

> **Bonus:** the response surface now lets the API report partial failure (`207 Multi-Status` or a structured 200 body), much friendlier for the frontend.

### F-5.4 🟡 `ValidationError` from Django used as a 422 marker
- **File:** `core/services.py`, `core/exceptions.py`
- **Observed:** Service raises `django.core.exceptions.ValidationError`; `custom_exception_handler` translates it to 422.
- **Risk:** The handler returns `None` when DRF doesn't handle and the exception isn't `DjangoValidationError`, which produces a 500 — fine, but the contract is implicit.
- **Fix (optional, cleaner long-term):** Define explicit domain exceptions in `core/exceptions.py`:

```python
class DomainError(Exception):
    status_code = 422

class InvalidStatusTransition(DomainError):
    pass
```

…and let the handler map them. This decouples your domain from `django.core.exceptions`.

---

## Phase 6 — ViewSets and Routers

### F-6.1 🟡 No `available` `@action` endpoint
- **Observed:** The plan included a public `GET /api/pets/available/` shortcut.
- **Risk:** Frontend hits `?status=available&page_size=20` instead — works, but you lose a stable route name (`reverse("pet-available")`) used by clients/tests.
- **Fix:**

```python
@action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
def available(self, request: Request) -> Response:
    pets = self.filter_queryset(self.get_queryset()).filter(
        status=PetStatus.AVAILABLE,
    )
    page = self.paginate_queryset(pets)
    serializer = self.get_serializer(page or pets, many=True)
    return (
        self.get_paginated_response(serializer.data) if page is not None
        else Response(serializer.data)
    )
```

### F-6.2 🟢 `PetViewSet.ordering = ["-name"]` overrides Meta
- **File:** `core/views.py:36`
- **Observed:** Default ordering is by name DESC, but `Pet.Meta.ordering = ["-created_at"]`.
- **Insight:** Probably an oversight — list-by-name is unusual. Either remove the line (model default wins) or change to `["-created_at"]` to match the model. If "name" was intentional, document why.

### F-6.3 🟢 `OrganizationViewSet` annotates `pet_count` on every action
- **File:** `core/views.py:23`
- **Observed:** `Count("pets")` runs on `retrieve` too (one organization at a time, fine), but also on `update`/`destroy` reads.
- **Insight:** Cheap query (single GROUP BY), low priority. If you ever need to expose org sizes in deeper aggregations, move this onto a manager method (`Organization.objects.with_pet_count()`) so it can be reused.

### F-6.4 🟡 Versioned URLs but no DRF versioning class
- **File:** `config/urls.py`
- **Observed:** `path("api/v1/", ...)` — versioning is by URL prefix only.
- **Risk:** When you launch v2, you'll need to maintain a parallel app. DRF's [`URLPathVersioning`](https://www.django-rest-framework.org/api-guide/versioning/) class lets the same view branch on `request.version`.
- **Fix (optional):** Add to `REST_FRAMEWORK`:

```python
"DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
"DEFAULT_VERSION": "v1",
"ALLOWED_VERSIONS": ["v1"],
```

…and switch the router include to `path("api/<str:version>/", ...)`.

---

## Phase 7 — JWT

### F-7.1 🟠 `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION` without the blacklist app
- **File:** `config/settings.py:104-106`, `INSTALLED_APPS`
- **Observed:** Both flags are `True` but `rest_framework_simplejwt.token_blacklist` is **not** in `INSTALLED_APPS`, no migrations for it, and `OutstandingToken`/`BlacklistedToken` tables don't exist.
- **Risk:** Rotated refresh tokens are silently **not** blacklisted — a stolen refresh token remains usable until expiry. Documented behavior of SimpleJWT.
- **Fix:**

```python
INSTALLED_APPS = [
    ...,
    "rest_framework_simplejwt.token_blacklist",
]
```

Then `manage.py migrate` and add the logout endpoint:

```python
# config/urls.py
from rest_framework_simplejwt.views import TokenBlacklistView

path("api/v1/auth/token/blacklist/", TokenBlacklistView.as_view(), name="token_blacklist"),
```

### F-7.2 🟢 Manual URL wiring instead of `simplejwt.urls`
- **Observed:** Token endpoints registered explicitly (cleaner than the bundled URLConf).
- **Insight:** Good practice — gives you control. Just keep them under the same namespace as `core.urls` (already done with `/api/v1/auth/`).

---

## Phase 8 — Permissions

### F-8.1 💡 `IsOwnerOrganizationOrReadOnly` checks M2M membership
- **File:** `core/permissions.py`
- **Observed:** Goes through `request.user.profile.organizations` instead of the plan's single `request.user.organization`.
- **Insight:** Strictly better. Document this in the docstring (and link to `Profile`):

```python
class IsOwnerOrganizationOrReadOnly(permissions.BasePermission):
    """
    Read: anyone (covered earlier in the chain).
    Write: only if the request.user is linked to obj's organization
    via `request.user.profile.organizations` (M2M).
    """
```

### F-8.2 🟡 Permission silently denies when `Profile` doesn't exist
- **File:** `core/permissions.py:27-30`
- **Observed:** `getattr(request.user, "profile", None)` returns `None` for users without a profile. Caller gets a generic 403.
- **Risk:** Couple to F-1.2 — superusers without a profile look "broken". Hard to debug.
- **Fix (after wiring the signal in F-1.2):** also short-circuit for `is_superuser`:

```python
if request.user.is_superuser:
    return True
profile = getattr(request.user, "profile", None)
if profile is None:
    return False
```

### F-8.3 🟡 `has_permission` allows GET unauthenticated
- **File:** `core/permissions.py:15`
- **Observed:** Returns `True` for SAFE methods even for anonymous users.
- **Insight:** Intentional — combined with `get_permissions()` returning `AllowAny()` for `list`/`retrieve` it works. Just add a comment so the next reader knows it's deliberate.

### F-8.4 🟡 No row-level filtering on `list`
- **Observed:** Anonymous (and any authenticated user) can list every pet from every organization.
- **Risk:** If pets become sensitive (medical data, owner contact info), object-level permissions don't help on a list endpoint. Use a queryset filter:

```python
def get_queryset(self) -> QuerySet[Pet]:
    qs = Pet.objects.with_organization()  # phase 11
    if self.action == "list" and not self.request.user.is_authenticated:
        return qs.filter(status=PetStatus.AVAILABLE)
    return qs
```

---

## Phase 9 — Filters, search, pagination

### F-9.1 🟢 `breed` icontains added (improvement)
- **Insight:** Nice DX win not in the plan; keep it.

### F-9.2 🟡 Page size is fixed at 20 globally
- **File:** `config/settings.py:122`
- **Observed:** No `PageNumberPagination` subclass with `page_size_query_param`.
- **Risk:** Consumers can't request `?page_size=100`. For a public listing app this matters.
- **Fix:**

```python
# core/pagination.py
from rest_framework.pagination import PageNumberPagination

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
```

…and reference it in `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`.

### F-9.3 🟡 `OrderingFilter` allows ordering by any indexed field?
- **Observed:** `ordering_fields = ["name", "created_at", "birth_date"]` — explicit allowlist. ✅
- **Insight:** Good. Keep it explicit; never set `ordering_fields = "__all__"` in production.

---

## Phase 10 — Performance: `select_related` / `prefetch_related`

### F-10.1 🟢 `select_related("organization")` correctly placed in `get_queryset`
- **File:** `core/views.py:40`
- **Insight:** ✅ Only one query for the Pet list. Verified by counting queries (you can confirm with `django.test.utils.override_settings(DEBUG=True)` + `connection.queries`).

### F-10.2 🟡 No `.only(...)` projection for list endpoint
- **File:** `core/views.py`
- **Observed:** Loads every column — fine today, painful when `description`/`temperament`/`image` start carrying real content.
- **Fix (later):** Provide a separate `PetListSerializer` and queryset:

```python
def get_queryset(self) -> QuerySet[Pet]:
    qs = Pet.objects.select_related("organization")
    if self.action == "list":
        return qs.only(
            "id", "name", "species", "size", "status", "image",
            "organization__id", "organization__name",
        )
    return qs
```

> Beware: `.only()` triggers extra queries if the serializer touches deferred fields. Pair it with a slim list serializer.

### F-10.3 🟡 `Profile.organizations` reverse access in permissions causes one query per request
- **File:** `core/permissions.py:32`
- **Observed:** `profile.organizations.all()` is a fresh query every time `has_object_permission` runs.
- **Fix:** When the request is authenticated, prefetch once:

```python
def get_queryset(self) -> QuerySet[Pet]:
    qs = Pet.objects.select_related("organization")
    if self.request.user.is_authenticated:
        qs = qs.prefetch_related("organization__profiles")  # if you need it
    return qs
```

…or cache the org IDs on the request:

```python
class IsOwnerOrganizationOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if not hasattr(request, "_user_org_ids"):
            profile = getattr(request.user, "profile", None)
            request._user_org_ids = (
                set(profile.organizations.values_list("id", flat=True))
                if profile else set()
            )
        target_org_id = obj.organization_id if hasattr(obj, "organization_id") else obj.id
        return target_org_id in request._user_org_ids
```

---

## Cross-cutting concerns (touch multiple phases)

### X-1 🔴 No tests yet
- **Observed:** `core/tests.py` and `core/tests/__init__.py` are effectively empty.
- **Risk:** Every refactor in phases 11–13 is a leap of faith. The bulk-update divergence (F-5.3) is exactly the kind of bug a 5-line test would have caught.
- **Fix:** Promoted to **Phase 12** in the roadmap. Start with a smoke test for each `@action` and a state-machine test for `services.change_status`.

### X-2 🟠 No CI pipeline
- **Observed:** `pre-commit-config.yaml` exists locally; nothing runs on PRs.
- **Risk:** `make lint` / `make test` are honor-system. F-0.1 (broken pytest config) would be caught instantly by CI.
- **Fix:** Add a `.github/workflows/ci.yml` that runs ruff, mypy and pytest against a Postgres + Redis service container.

### X-3 🟡 No `core/admin.py` registrations
- **Observed:** Admin loads but nothing is browsable.
- **Fix (one minute):**

```python
from django.contrib import admin
from .models import Organization, Pet, Profile

admin.site.register([Organization, Pet, Profile])
```

…and customize with `list_display` / `list_filter` once the data model stabilizes.

### X-5 🟡 `TIME_ZONE = "UTC"` + `USE_TZ = True` — good, but no explicit Celery TZ
- **File:** `config/celery.py`
- **Risk:** Mixed TZ between Django (UTC) and Celery (default UTC, fine) — explicit is better.
- **Fix:** `app.conf.timezone = "UTC"` and `app.conf.enable_utc = True` in `config/celery.py`.

### X-6 🟢 Type-ignore comments scattered (`# type: ignore[type-arg]`)
- **Observed:** Mostly on `viewsets.ModelViewSet` — a known `django-stubs` / `djangorestframework-stubs` gap.
- **Insight:** Acceptable. Centralize them with a typed alias:

```python
# core/_typing.py
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rest_framework.viewsets import ModelViewSet as ModelViewSet
else:
    from rest_framework.viewsets import ModelViewSet
```

Or simply prefer the `# type: ignore` comments at the class level once and move on.

### X-8 🟢 Spanish/English mixing in code & docs
- **Observed:** `learning-plan.md` is Spanish, code comments are English, `requests.http` mixes both.
- **Insight:** Pick one for code (English is standard) and document the choice in the README so contributors don't second-guess.

---

## Ranked action list (P0 → P3)

> A pragmatic order if you only have one afternoon to triage everything before starting Phase 11.

**P0 — Stop the bleeding (≈ 1h)**
1. F-7.1 — Install `token_blacklist` app → real security fix.
2. F-1.2 — Add `Profile` auto-creation signal → unblocks any new authenticated user.
3. F-5.2 — Wrap Celery `delay()` calls in `transaction.on_commit` → fixes the race.
4. F-5.3 — Fix `bulk_update_status` (`updated_at` + missing notifications + report skipped/not_found).

**P1 — Consistency & correctness (≈ half-day)**
5. F-3.1 — Restore nested-org-read + `*_display` fields in `PetSerializer`.
6. F-3.2, F-4.1 — Replace status string literals with `PetStatus` references.
7. F-1.5 — Add DB indexes on filter columns.
8. F-6.1 — Add `available` action.
9. X-3 — Register admin classes.

**P2 — Production hardening (≈ 1 sprint)**
10. X-2 — CI pipeline (ruff + mypy + pytest with Postgres service).
11. X-5 — Explicit Celery `timezone` / `enable_utc`.

**P3 — Polish & DX**
12. F-2.1 — Wire up `PetSearchFilters` (or delete it).
13. F-4.2 — Use `BreedInfo` or delete it.
14. F-6.4 — Add DRF versioning class.
15. F-9.2 — Configurable page size.
16. F-10.2 — Slim list serializer with `.only()`.
17. F-10.3 — Cache user-org IDs on the request to remove the per-check DB hit.

---

## Glossary of the references used

- **Django docs:** Field options (`db_index`, `Meta.indexes`), Signals, `transaction.on_commit`, `bulk_update`, model managers.
- **DRF docs:** ViewSets `get_queryset` / `get_permissions`, `@action`, custom pagination, `URLPathVersioning`.
- **SimpleJWT docs:** `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` requirements.
- **Pydantic v2 docs:** `field_validator`, `model_validator`, `BaseSettings`.
- **Two Scoops of Django** (community standard): split settings, fat models / thin views, service layer.
