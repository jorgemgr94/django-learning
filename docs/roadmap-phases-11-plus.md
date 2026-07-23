# ConectaPelu2 — Roadmap from Phase 11 onwards

> **Context:** Phases 0–10 are implemented in `core/` and `config/`. The original
> learning plan (`docs/learning-plan.md`) had three more phases (11–13) and a
> *"Próximos pasos (v2)"* backlog. This document re-shapes that backlog around
> the **current** code, fixes the dependencies between phases, and turns each
> step into a self-contained, executable mini-project.
>
> Phases are numbered in **execution order**: do them top to bottom. The
> numbers are no longer carried over from the original `learning-plan.md` —
> see the mapping table at the very bottom for the cross-reference.
>
> Each phase has:
> - **Why now** — what the project gains.
> - **Pre-requisites** — links to findings in
>   [`phases-1-10-findings.md`](./phases-1-10-findings.md) (e.g. `F-0.1`).
>   Don't start a phase until its blockers are green.
> - **Deliverables** — concrete files / endpoints / commands.
> - **Verification** — how you prove the phase landed.

---

## At a glance

| Phase | Theme | Status in repo | Blockers (findings) |
|------:|-------|----------------|---------------------|
| 11 | Managers & custom QuerySets | Stub fields only (`objects: Manager[Pet]`) | — |
| 12 | Test suite (pytest + factory-boy) | `core/tests/` empty | F-0.1 |
| 13 | Celery + Redis (real tasks) | Infra ✅, body of `notify_status_change` is empty | F-5.2, F-5.3 |
| 14 | Celery Beat (periodic) | Not started | Phase 13 |
| 15 | Cloud storage (S3 / DigitalOcean Spaces) | Image is a `URLField` today | — |
| 16 | Production-ready settings & full Docker stack | Single `settings.py` | F-0.2, F-0.7 |
| 17 | API documentation (drf-spectacular) | Not started | Phase 12 |
| 18 | Caching with Redis | Not started | Phase 13 (Redis already up) |
| 19 | Throttling & security hardening | Not started | Phase 16 (split settings) |
| 20 | Django Async (ASGI views & ORM) | ASGI stub `config/asgi.py` | — |
| 21 | CI/CD with GitHub Actions | Not started | Phase 12 |

> **Why this ordering:**
> - **12 (tests) early** — every later phase rides on it, and the bug surface in
>   phases 11/13 is exactly what tests are good at catching.
> - **15 (cloud storage) before 16 (prod settings)** — `ImageField`,
>   `django-storages`, presigned URLs, `Pillow` validation and `MEDIA_URL`
>   semantics are dense Django-specific surface that's worth meeting before
>   you split settings around it.
> - **20 (async) second-to-last** — async Django is mostly "which ORM methods
>   have an `a*` prefix and where `sync_to_async` goes." If you're already
>   fluent with event loops in another stack, the marginal Django-specific
>   learning here is small. Don't gate later phases on it.
> - **21 (CI) last** — it gates everything, so it has to come after everything
>   it's expected to enforce.

---

## Phase 11 — Managers & custom QuerySets

> **Mental model:** `Pet.objects` **is** a manager. By customizing it, you push
> reusable query logic next to the model — out of views and services — and you
> get a chainable, domain-named API (`Pet.objects.available().for_organization(1)`).

### Why now
- `core/views.py` already has the same query logic in two places (`PetViewSet.get_queryset`, `OrganizationViewSet.get_queryset`).
- `core/models.py` already has the type stub `objects: models.Manager["Pet"]` waiting to be replaced with a real `PetManager`.
- All fixes to N+1 issues land here once and benefit every caller.

### Deliverables

**1. `core/managers.py`** — new file, two classes:

```python
from __future__ import annotations
from django.db import models
from django.db.models import Count

# Avoid circular imports; reference strings in get_queryset.

class PetQuerySet(models.QuerySet["Pet"]):
    """Chainable queryset. Each method returns a queryset so you can
    keep filtering: Pet.objects.available().by_species("dog").
    """

    def available(self) -> "PetQuerySet":
        from .models import PetStatus
        return self.filter(status=PetStatus.AVAILABLE)

    def archived(self) -> "PetQuerySet":
        from .models import PetStatus
        return self.filter(status=PetStatus.ARCHIVED)

    def by_species(self, species: str) -> "PetQuerySet":
        return self.filter(species=species)

    def for_organization(self, organization_id: int) -> "PetQuerySet":
        return self.filter(organization_id=organization_id)

    def with_organization(self) -> "PetQuerySet":
        return self.select_related("organization")

    def older_than_days(self, days: int) -> "PetQuerySet":
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=days)
        return self.filter(updated_at__lt=cutoff)


class PetManager(models.Manager["Pet"]):
    """Public manager. Forwards key methods to the queryset so calls
    like `Pet.objects.available()` work identically to `.get_queryset().available()`.
    """

    def get_queryset(self) -> PetQuerySet:
        # Default: every queryset includes the FK join. Cheap and avoids
        # accidental N+1 on every caller.
        return PetQuerySet(self.model, using=self._db).with_organization()

    # Direct surface
    def available(self) -> PetQuerySet:
        return self.get_queryset().available()

    def for_organization(self, organization_id: int) -> PetQuerySet:
        return self.get_queryset().for_organization(organization_id)


class OrganizationQuerySet(models.QuerySet["Organization"]):
    def with_pet_count(self) -> "OrganizationQuerySet":
        return self.annotate(pet_count=Count("pets"))


OrganizationManager = models.Manager.from_queryset(OrganizationQuerySet)
```

> **`Manager.from_queryset(...)`** is the shortcut when the manager has no
> behavior beyond exposing the queryset methods. Use it for `Organization`
> to keep the file lean.

**2. `core/models.py`** — wire the managers (replaces today's type stubs):

```python
from .managers import PetManager, OrganizationManager

class Organization(models.Model):
    ...
    objects = OrganizationManager()  # type: ignore[misc]


class Pet(models.Model):
    ...
    objects = PetManager()  # type: ignore[misc]
```

> Drop the `objects: models.Manager["Pet"]` stub line — the real assignment
> gives mypy/django-stubs the same information.

**3. `core/views.py`** — refactor to use the managers:

```python
class PetViewSet(viewsets.ModelViewSet):
    ...
    def get_queryset(self) -> QuerySet[Pet]:
        # Manager already select_relateds organization
        return Pet.objects.all()


class OrganizationViewSet(viewsets.ModelViewSet):
    ...
    def get_queryset(self) -> QuerySet[Organization]:
        return Organization.objects.with_pet_count()
```

**4. `core/services.py`** — adopt manager methods where it improves intent:

```python
def archive_old_submissions(days: int = 90) -> int:
    """Archive submitted pets that have been pending for more than `days` days."""
    deleted, _ = (
        Pet.objects.filter(status=PetStatus.SUBMITTED).older_than_days(days).delete()
    )
    return deleted
```

### Verification
- `manage.py shell`:
  ```python
  from core.models import Pet
  qs = Pet.objects.available().by_species("dog")
  print(qs.query)         # SELECT … FROM core_pet INNER JOIN core_organization …
  print(len(qs))          # one query (verify with connection.queries length)
  ```
- mypy: type of `Pet.objects.available()` is `PetQuerySet`, autocompleted.

### Common pitfalls
- **Manager replacement breaks `objects.all()` in migrations.** Django records
  managers in migrations only when `use_in_migrations = True`. For a default
  manager replacement you don't need it; just be aware before running
  `makemigrations` after this change. See
  [Django docs — Custom managers and migrations](https://docs.djangoproject.com/en/5.2/topics/migrations/#model-managers).
- **`from_queryset` collapses two classes into one** — fine when there's no
  manager-only logic. If you later need `Manager.create_default_org()`, switch
  to a real subclass.

---

## Phase 12 — Tests with `pytest-django` + `factory-boy`

> Promoted from the "Próximos pasos (v2)" backlog because the empty
> `core/tests/` directory makes every later phase risky.

### Why now
- The `pyproject.toml` already lists `pytest`, `pytest-django`, `pytest-cov`, `factory-boy` (see `[dependency-groups].dev`).
- Without tests, finding **F-5.3** (the bulk-update bug) was lucky. The next bug like that should be caught by the test suite.
- Phase 11's manager refactor needs assertions: "did `Pet.objects.available()` produce one query, not N+1?" — `django_assert_num_queries` makes that trivial.

### Pre-requisites
- **F-0.1** fixed (`DJANGO_SETTINGS_MODULE` correctly points at `config.settings`).

### Deliverables

**1. Layout:**

```
core/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── factories.py
│   ├── test_models.py
│   ├── test_serializers.py
│   ├── test_services.py        # state machine
│   ├── test_permissions.py
│   ├── test_views_pets.py      # APIClient: list/retrieve/create/change-status/bulk
│   └── test_tasks.py           # Celery in eager mode (placeholder until Phase 13)
```

**2. `core/tests/conftest.py`:**

```python
import pytest
from rest_framework.test import APIClient
from .factories import UserFactory, OrganizationFactory, PetFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def org(db):
    return OrganizationFactory()


@pytest.fixture
def pet(db, org):
    return PetFactory(organization=org)


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client
```

**3. `core/tests/factories.py`:**

```python
import factory
from django.contrib.auth import get_user_model
from core.models import Organization, Pet, Profile, PetStatus

User = get_user_model()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@test.com")
    password = factory.PostGenerationMethodCall("set_password", "passw0rd!")


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization
    name = factory.Sequence(lambda n: f"Shelter {n}")
    email = factory.LazyAttribute(lambda o: f"{o.name.lower().replace(' ', '')}@test.com")


class PetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pet
    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Faker("first_name")
    species = "dog"
    sex = "male"
    size = "medium"
    status = PetStatus.SUBMITTED
```

**4. `core/tests/test_services.py`** — state machine sanity:

```python
import pytest
from django.core.exceptions import ValidationError
from core.models import PetStatus
from core import services
from .factories import PetFactory


@pytest.mark.django_db
def test_change_status_allowed_transition(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True  # run task synchronously
    pet = PetFactory(status=PetStatus.SUBMITTED)
    services.change_status(pet, PetStatus.AVAILABLE)
    pet.refresh_from_db()
    assert pet.status == PetStatus.AVAILABLE


@pytest.mark.django_db
def test_change_status_invalid_transition_raises():
    pet = PetFactory(status=PetStatus.ARCHIVED)
    with pytest.raises(ValidationError):
        services.change_status(pet, PetStatus.AVAILABLE)
```

**5. `core/tests/test_views_pets.py`** — endpoint contract & N+1 regression net:

```python
import pytest
from rest_framework import status
from .factories import PetFactory


@pytest.mark.django_db
def test_list_pets_anonymous(api_client):
    PetFactory.create_batch(3)
    resp = api_client.get("/api/v1/pets/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 3


@pytest.mark.django_db
def test_list_pets_does_not_n_plus_one(api_client, django_assert_num_queries):
    PetFactory.create_batch(10)  # 10 pets across many orgs
    # 1 for COUNT (paginator), 1 for the SELECT … JOIN organization. Auth might add 1.
    with django_assert_num_queries(3):
        api_client.get("/api/v1/pets/")


@pytest.mark.django_db
def test_create_pet_requires_auth(api_client, org):
    resp = api_client.post(
        "/api/v1/pets/",
        {"organization": org.id, "name": "Kira", "species": "dog", "sex": "female", "size": "small"},
        format="json",
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
```

**6. `pyproject.toml` test settings** (after F-0.1 / F-0.2):

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"   # once split settings exist (Phase 16)
python_files = ["tests.py", "test_*.py", "*_tests.py"]
addopts = "-ra --strict-markers --cov=core --cov-report=term-missing"

[tool.coverage.run]
branch = true
source = ["core", "config"]
omit = ["**/migrations/**", "**/tests/**"]
```

**7. Test settings module** (`config/settings/test.py`, lands fully in Phase 16):

```python
from .base import *  # noqa
DATABASES["default"]["NAME"] = "test_pets_db"     # fast-path
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # 50× faster
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

> Until Phase 16 splits settings, point pytest at `config.settings` and set
> the eager flags via `settings` fixtures or env vars.

### Verification
- `make test` produces an HTML coverage report at `htmlcov/index.html`.
- Coverage gate: **≥ 70%** on `core/services.py`, `core/permissions.py`, `core/views.py` (the layers with real risk).

### Common pitfalls
- **`Profile` not auto-created** — see `F-1.2`. Add `profile=ProfileFactory(...)` post-generation, or fix the signal first.
- **`force_authenticate` skips JWT.** Good for unit tests; add a separate
  `test_auth.py` that drives the JWT endpoints directly.
- **`django_assert_num_queries` is your N+1 alarm.** Use it on every list-style endpoint.

---

## Phase 13 — Celery + Redis (turning the stub into a real background pipeline)

> **State today:**
> - `config/celery.py` boots Celery and reads `CELERY_*` from settings.
> - `core/tasks.py` defines `notify_status_change` with an **empty body**
>   (it logs nothing, returns nothing).
> - `core/services.py` already calls `.delay(...)` — but the result is a no-op,
>   and (per finding **F-5.2**) the call happens before the DB transaction commits.
>
> Phase 13 turns this into a real notification pipeline.

### Why now
- Without a working task body, the Celery worker is a placeholder you can't trust.
- Fixing F-5.2 / F-5.3 here lands the race condition fix where it actually matters (background processing).
- Tests (Phase 12) are already in place to cover the `transaction.on_commit` path with `pytest.mark.django_db(transaction=True)`.

### Pre-requisites
- **F-5.2** — wrap `.delay()` in `transaction.on_commit`.
- **F-5.3** — bulk update fires per-pet notifications on commit.

### Deliverables

**1. `core/tasks.py`** — implement the real task using `@shared_task`:

```python
from __future__ import annotations
from typing import Any
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,    # cap exponential backoff at 10 min
    retry_jitter=True,
    max_retries=5,
    acks_late=True,           # ack only after the task succeeds
)
def notify_status_change(self, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Notify external systems (email, Slack, webhook) when a pet status changes.
    The payload is validated again here — Pydantic is the contract between
    the producer (service) and the consumer (this task).
    """
    from .schemas import PetStatusChangedPayload  # local import: avoids ORM during worker boot
    data = PetStatusChangedPayload(**payload)

    logger.info(
        "Pet %s: %s → %s by user %s",
        data.pet_id, data.old_status, data.new_status, data.changed_by_user_id,
    )

    # Real-world side effects would go here: send_mail / requests.post / etc.
    return {
        "pet_id": data.pet_id,
        "transition": f"{data.old_status} → {data.new_status}",
        "notified": True,
    }


@shared_task
def cleanup_archived_pets(days: int = 365) -> int:
    """
    Delete pets archived more than `days` days ago.
    Runs on Celery Beat (Phase 14).
    """
    from .models import Pet, PetStatus
    return Pet.objects.filter(status=PetStatus.ARCHIVED).older_than_days(days).delete()[0]
```

> **Why `@shared_task` instead of `@app.task`:** decouples the task from the
> celery app instance — cleaner for tasks defined inside Django apps, easier
> to test, and the recommendation in
> [the Celery docs](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html#using-the-shared-task-decorator).

**2. `core/services.py`** — defer firing until commit (closes F-5.2):

```python
from django.db import transaction

def change_status(pet: Pet, new_status: PetStatus, changed_by_user_id: int | None = None) -> Pet:
    ...
    pet.save(update_fields=["status", "updated_at"])

    payload = PetStatusChangedPayload(
        pet_id=pet.id, old_status=old_status, new_status=new_status,
        changed_by_user_id=changed_by_user_id,
    )

    # Only enqueue if the transaction commits successfully
    transaction.on_commit(
        lambda: notify_status_change.delay(payload.model_dump())
    )
    return pet
```

**3. `config/celery.py`** — be explicit about timezone & UTC:

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("conectapelu2")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # safer for long-ish tasks
)
```

**4. Settings hardening** — add to `config/settings.py`:

```python
CELERY_TASK_ALWAYS_EAGER = False          # explicit, set True only in test settings
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True  # silence Celery 6.0 warning
```

**5. Worker process** — keep your local flow with `make worker`, but document:

```bash
# Health check: enqueue and wait for a result
uv run python manage.py shell -c "
from core.tasks import notify_status_change
r = notify_status_change.delay({'pet_id': 1, 'old_status': 'submitted', 'new_status': 'available'})
print(r.get(timeout=10))
"
```

### Verification
- `django_celery_results` admin (`/admin/` → Task Results) shows successful runs.
- Trigger a `change-status` request and confirm the worker logs include the transition line.
- Manually rollback a transaction in `manage.py shell` and confirm **no** task fires.
- New test in `test_tasks.py` asserting that a rolled-back transaction does not enqueue a task (use `pytest.mark.django_db(transaction=True)`).

### Common pitfalls
- **`acks_late=True` requires idempotent tasks.** A status notification is fine to retry; sending an SMS would not be — split the side effects.
- **`retry_backoff=True` overrides `default_retry_delay`.** Drop the manual `self.retry(countdown=...)` from the original plan.
- **Pydantic in a worker = imports cost.** Use `from .schemas import …` inside the task, not at module top, so that `celery -A config inspect ping` boots fast.

---

## Phase 14 — Celery Beat (scheduled tasks)

> Originally a v2 backlog item. Bumped to a phase of its own because
> `cleanup_archived_pets` already lives in `core/tasks.py` (Phase 13) and is
> begging for a schedule.

### Why now
- Demonstrates the **scheduling** facet of Celery without dragging in a separate framework (cron, APScheduler).
- Validates that the worker container will need a sibling **beat** container in Phase 16.

### Deliverables

**1. Add `django-celery-beat`:**

```bash
uv add django-celery-beat
```

```python
# config/settings.py
INSTALLED_APPS = [
    ...,
    "django_celery_beat",
]

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
```

```bash
uv run python manage.py migrate
```

**2. Schedule the cleanup from the admin** (no code schedule):
- `/admin/django_celery_beat/periodictask/add/`
- Task: `core.tasks.cleanup_archived_pets`
- Schedule: cron entry `0 3 * * *` (03:00 UTC daily)

**3. Local beat process:**

```bash
uv run celery -A config beat --loglevel=info
```

> Add a `make beat` target.

### Verification
- After 3 minutes of idle, run a cron entry every minute (just for testing) and watch the worker log fire `cleanup_archived_pets`.
- The `PeriodicTask` admin shows last run time updating.

---

## Phase 15 — Cloud storage for images (`django-storages` + S3)

> Today, `Pet.image` is a `URLField` — the project just stores a URL pointing
> wherever the user uploaded the file. This phase makes the API a first-class
> uploader, and surfaces a lot of Django-specific surface area you don't get
> elsewhere: `ImageField` validation, `MEDIA_URL` semantics, presigned URLs,
> the fact that `model.delete()` does **not** delete the underlying file, and
> multipart parsing in DRF.

### Deliverables

```bash
uv add 'django-storages[s3]' boto3 Pillow
```

**1. Replace `image` with an `ImageField` (and a forward-compat field):**

```python
class Pet(models.Model):
    ...
    image_url = models.URLField(blank=True, default="")           # legacy, keep for one release
    image = models.ImageField(upload_to="pets/", blank=True, null=True)
```

> Two-step migration: keep both fields for one release, then drop `image_url`.
> This is your chance to practice **expand-and-contract** migrations end to
> end (add column → backfill → switch reads → drop column).

**2. Backend config:**

```python
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env.AWS_STORAGE_BUCKET_NAME,
            "region_name": env.AWS_S3_REGION_NAME,
            "default_acl": None,
            "querystring_auth": True,    # presigned URLs
            "querystring_expire": 3600,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
```

**3. Env vars:**

Add `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` to `config/env.py` and `.env.example`.

**4. Lifecycle hook** to delete the S3 object when a `Pet` is deleted:

```python
from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=Pet)
def delete_pet_image(sender, instance: Pet, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
```

> This is the gotcha: by default, `pet.delete()` removes the row but leaves
> the file in S3. Worth showing in tests.

### Verification
- `POST /api/v1/pets/` with multipart form data containing `image` → object lands in S3, the response shows a presigned URL.
- `DELETE /api/v1/pets/{id}/` → the S3 object is gone (verify with `aws s3 ls`).

### Common pitfalls
- **`Pillow` raises during validation, not on save.** Catch
  `django.core.exceptions.ValidationError` and surface a 400 in the serializer.
- **Don't store the absolute URL in the DB.** Let `ImageField.url` compute it
  on each access, so you can rotate buckets without a migration.

---

## Phase 16 — Production-ready settings & full Docker stack

> Combines the original v2 item *"Docker Compose full-stack"* with the
> findings F-0.2, F-0.7, X-4 and X-7. This is the phase where the project
> finally has a deployable shape.

### Deliverables

**1. Split settings:**

```
config/settings/
├── __init__.py
├── base.py        # everything currently in config/settings.py
├── local.py       # DEBUG=True, console email, SQL logging, debug toolbar
├── production.py  # security headers, CONN_MAX_AGE, gunicorn workers
└── test.py        # see Phase 12
```

`local.py` re-introduces SQL logging on `django.db.backends` so the
`select_related` discipline you locked in during Phase 11 is visible.

`production.py` flips on `CONN_MAX_AGE`, `SECURE_*` headers, `ALLOWED_HOSTS`
strictness, etc. — see finding **X-4** for the full block.

**2. Containerized worker + beat in `docker-compose.yml`:**

```yaml
  app:
    build: .
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"
    command: ["uv", "run", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

  worker:
    build: .
    env_file: .env
    depends_on:
      - redis
      - db
    command: ["uv", "run", "celery", "-A", "config", "worker", "--loglevel=info"]

  beat:
    build: .
    env_file: .env
    depends_on:
      - redis
      - db
    command: ["uv", "run", "celery", "-A", "config", "beat", "--loglevel=info",
              "--scheduler", "django_celery_beat.schedulers:DatabaseScheduler"]
```

**3. Hardened `Dockerfile`:**

```dockerfile
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --uid 1000 --create-home app
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=app:app . .
USER app

EXPOSE 8000
CMD ["uv", "run", "gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
```

### Verification
- `docker compose up --build` brings up `db`, `redis`, `app`, `worker`, `beat` healthy.
- `manage.py check --deploy` passes inside the production-config container.
- `pytest` now runs against `config.settings.test` cleanly.

---

## Phase 17 — API documentation with `drf-spectacular`

### Why now
- Tests (Phase 12) lock the contract; documentation publishes it.
- Returns OpenAPI 3.1 — what a frontend or external consumer expects in 2026.
- Settings are now split (Phase 16), so `SPECTACULAR_SETTINGS` lives in `base.py` cleanly.

### Deliverables

```bash
uv add drf-spectacular
```

```python
# config/settings/base.py
INSTALLED_APPS += ["drf_spectacular"]
REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"

SPECTACULAR_SETTINGS = {
    "TITLE": "ConectaPelu2 API",
    "DESCRIPTION": "Pet adoption platform — DRF reference implementation",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
```

```python
# config/urls.py
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns += [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
```

For the custom `@action` endpoints with non-trivial payloads, attach explicit
serializers (see finding **F-3.3**) so Spectacular renders them properly:

```python
from drf_spectacular.utils import extend_schema

@extend_schema(request=BulkStatusUpdateRequestSerializer, responses=BulkStatusUpdateResponseSerializer)
@action(detail=False, methods=["post"], url_path="bulk-status")
def bulk_status_update(self, request): ...
```

### Verification
- `/api/docs/` renders Swagger with every endpoint and example payload.
- `manage.py spectacular --file schema.yaml` produces a clean YAML — no warnings.

---

## Phase 18 — Caching with Redis

> Redis is already part of `docker-compose.yml`; we're just adding a second
> use case beyond the Celery broker.

### Deliverables

```bash
uv add django-redis
```

```python
# config/settings/base.py
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env.REDIS_URL.replace("/0", "/1"),  # use DB 1 for cache
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "TIMEOUT": 300,
    }
}
```

**Cache the `available` listing endpoint:**

```python
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers

class PetViewSet(viewsets.ModelViewSet):
    ...
    @method_decorator(cache_page(60))
    @method_decorator(vary_on_headers("Accept-Language", "Authorization"))
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def available(self, request):
        ...
```

**Manual invalidation in the service layer** — when `change_status` flips
to/from `available`:

```python
from django.core.cache import cache
cache.delete_pattern("*pets-available*")
```

### Verification
- First request to `/api/v1/pets/available/` — N queries, ~Y ms.
- Second within 60 s — 0 queries, ~ms.
- `redis-cli -p 6380 -n 1 keys '*'` shows the cached page.

---

## Phase 19 — Throttling & security hardening

### Deliverables

**Per-user / per-IP rate limits:**

```python
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
    "rest_framework.throttling.UserRateThrottle",
    "rest_framework.throttling.AnonRateThrottle",
]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "user": "200/min",
    "anon": "60/min",
    "login": "5/min",  # custom scope below
}
```

**Stricter scope on the login endpoint:**

```python
from rest_framework.throttling import ScopedRateThrottle

class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
```

…and replace the URL wiring in `config/urls.py`.

**Production security headers** (in `config/settings/production.py`, landed in Phase 16):

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
```

**`manage.py check --deploy`** — gate on this in CI (Phase 21).

### Verification
- `for i in $(seq 70); do curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/pets/; done` shows 429s after the threshold.

---

## Phase 20 — Django Async (ASGI, async views & ORM)

> **State today:** `config/asgi.py` is the auto-generated stub. No async views,
> no `aget`/`afilter` calls, no Channels.

### Why now (and when **not** now)
- This phase is the most experimental of the bunch. DRF's async support
  has been incrementally arriving since 3.15; full ViewSet async parity
  is still a work in progress. Treat this phase as a **lab** — not as
  the new default for production endpoints.
- Coming from a JS/Go background, the *concepts* (event loop, structured
  concurrency, `await`) transfer for free. What you're learning here is
  Django-specific: which ORM methods have async equivalents, where
  `sync_to_async` belongs, what breaks in DRF.

### Pre-requisites
- Phase 13 stable (Celery is the right tool for CPU-bound or long-running work).
- A real I/O-bound use case to justify it (external HTTP integration, SSE, WebSockets).

### Deliverables

**1. Add an ASGI server:**

```bash
uv add uvicorn[standard]
```

```bash
# Local
uv run uvicorn config.asgi:application --reload

# Make target
serve-async:
\tuv run uvicorn config.asgi:application --reload
```

**2. Async-ready Dockerfile entry point** — add a separate stage (don't replace gunicorn yet):

```dockerfile
CMD ["uv", "run", "uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]
```

**3. An async DRF view via `adrf`** (the de-facto bridge until DRF ships native support):

```bash
uv add adrf
```

```python
# core/views_async.py
import asyncio
import httpx
from adrf.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .schemas import BreedInfo  # finally has a use!


class BreedLookupView(APIView):
    permission_classes = [AllowAny]

    async def get(self, request, breed: str):
        # Two async I/O calls in parallel — the value-add of async views
        async with httpx.AsyncClient(timeout=5) as client:
            r1, r2 = await asyncio.gather(
                client.get(f"https://api.thedogapi.com/v1/breeds/search?q={breed}"),
                client.get(f"https://api.thecatapi.com/v1/breeds/search?q={breed}"),
            )
        # Validate every external response with Pydantic
        candidates = [
            BreedInfo(**item)
            for resp in (r1, r2) if resp.status_code == 200
            for item in resp.json()[:5]
        ]
        return Response([c.model_dump() for c in candidates])
```

```python
# core/urls.py
from django.urls import path
from .views_async import BreedLookupView

urlpatterns = router.urls + [
    path("breeds/<str:breed>/", BreedLookupView.as_view(), name="breed-lookup"),
]
```

**4. Async ORM access in a task or view:**

```python
async def latest_available_async(limit: int = 10) -> list[dict]:
    from core.models import Pet
    pets = []
    async for pet in Pet.objects.available()[:limit]:
        pets.append({"id": pet.id, "name": pet.name})
    return pets
```

### Verification
- `curl http://localhost:8000/api/v1/breeds/labrador/` returns combined results.
- During the request, the server keeps handling other requests (run two `curl`s in parallel and confirm they don't serialize).

### Common pitfalls & traps
- **Don't mix sync ORM in async views.** Wrap legacy sync helpers with
  `sync_to_async(...)`, or you'll see `SynchronousOnlyOperation`.
- **DRF browsable API is sync.** Some viewset features (filter backends,
  pagination classes) don't work end-to-end in async yet — `adrf` is the
  pragmatic compromise.
- **Heavy CPU work belongs in Celery (Phase 13), not async views.** Async
  helps with concurrency, not with CPU saturation.

---

## Phase 21 — CI/CD with GitHub Actions

### Why now
- Locks all of the above. PRs that break tests, types or migrations are
  rejected automatically.

### Deliverables

`.github/workflows/ci.yml` (sketch):

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_PASSWORD: postgres }
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy .
      - run: uv run python manage.py check --deploy --fail-level=WARNING
        env: { DJANGO_SETTINGS_MODULE: config.settings.production, SECRET_KEY: ci-secret-key }
      - run: uv run pytest --cov=core --cov-fail-under=70
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          DB_HOST: localhost
          REDIS_URL: redis://localhost:6379/0
```

---

## Cross-phase concerns to keep in mind

### Coding conventions to keep stable
- **Module-level service functions**, not classes (already chosen — keep it).
- **Pydantic for everything that crosses a network or process boundary** (Celery payload, external API). DRF serializers for HTTP request/response only.
- **`from __future__ import annotations`** on new files so forward references work without quotes.
- **`mypy --strict`** — no new `# type: ignore` without an issue link in the comment.

### Documentation hygiene
- Each new phase should append to `README.md` *Quickstart* the **one** new
  command it introduces (`make worker`, `make beat`, `make serve-async`, etc.).
- When you remove dead code (Phase 11 onwards), delete it; do not leave
  commented-out blocks.

### When you finish each phase
1. Open a PR with the phase number in the title (`feat(11): managers and querysets`).
2. Update this file's **At a glance** table (status column).
3. Make sure the corresponding finding in `phases-1-10-findings.md` is checked off.

---

## Cross-reference: original learning-plan.md ↔ this roadmap

> The numbering in this document **does not** carry over from the original
> `docs/learning-plan.md`. Use this table to translate between the two.

| Theme | `learning-plan.md` | This roadmap |
|-------|--------------------|--------------|
| Managers & QuerySets | Fase 11 | **Phase 11** |
| Celery + Redis (real tasks) | Fase 12 | **Phase 13** |
| Django Async / ASGI | Fase 13 | **Phase 20** |
| Tests with `pytest-django` + `factory-boy` | v2 (Próximos pasos) | **Phase 12** |
| Celery Beat for `cleanup_archived_pets` | v2 (Próximos pasos) | **Phase 14** |
| Caché con Redis (`django-redis`, `cache_page`) | v2 (Próximos pasos) | **Phase 18** |
| Documentación automática (`drf-spectacular`) | v2 (Próximos pasos) | **Phase 17** |
| Docker Compose full-stack | v2 (Próximos pasos) | **Phase 16** |
| Archivos en Cloud (`django-storages` + S3) | v2 (Próximos pasos) | **Phase 15** |
| Throttling | v2 (Próximos pasos) | **Phase 19** |
| Production settings split, security headers | (new) | **Phase 16** + **Phase 19** |
| CI/CD | (new) | **Phase 21** |
