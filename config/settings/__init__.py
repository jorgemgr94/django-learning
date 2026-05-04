"""Split Django settings package.

Set ``DJANGO_SETTINGS_MODULE`` to one of:

- ``config.settings.local`` — development (default in ``manage.py`` / ``.env``)
- ``config.settings.production`` — deployment (Dockerfile sets this)
- ``config.settings.test`` — ``pytest`` / CI
"""
