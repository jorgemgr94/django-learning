# ConectaPelu2 API 🐾
## 🚀 Tech Stack

- **Framework:** Django 5.2 + Django REST Framework
- **Database:** PostgreSQL
- **Caching & Brokers:** Redis
- **Async Tasks:** Celery
- **Validation:** Pydantic (Environment variables and complex payloads)
- **Tooling:** `uv` (lightning-fast package manager), `Ruff` (linter/formatter), `Mypy` (strict type-checking)
- **Infrastructure:** Docker Compose

---

## 🛠️ Quickstart

### Prerequisites
Make sure you have the following installed:
- [Docker & Docker Compose](https://www.docker.com/)
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `make` (Standard on macOS/Linux)

### 1. Initial Setup

Bootstrap the entire project, install dependencies, spin up the databases, and run migrations in one command:

```bash
make setup
```

### 2. Start the Development Server

```bash
make serve
```

The API will be available at `http://127.0.0.1:8000/`.

### Settings modules

Django settings live under `config/settings/`:

| `DJANGO_SETTINGS_MODULE` | Use case |
|------------------------|----------|
| `config.settings.local` | Default for `manage.py`, Celery, and local `.env` — `DEBUG`, SQL query logging |
| `config.settings.production` | Docker image / real deploy — HTTPS headers, `CONN_MAX_AGE` |
| `config.settings.test` | `pytest` (see `pyproject.toml`) |

Copy `.env.example` to `.env` and set at least `SECRET_KEY`. `ALLOWED_HOSTS` accepts comma-separated hosts or a JSON list.
