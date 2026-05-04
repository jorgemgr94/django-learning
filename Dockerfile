FROM python:3.12-slim-trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

RUN useradd --uid 1000 --create-home app

WORKDIR /app
# WORKDIR creates /app as root; app must own it to create `.venv`.
RUN chown app:app /app

COPY --chown=app:app pyproject.toml uv.lock ./
USER app
RUN uv sync --frozen --no-dev

COPY --chown=app:app . .

EXPOSE 8000
ENV DJANGO_SETTINGS_MODULE=config.settings.production

CMD ["uv", "run", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
