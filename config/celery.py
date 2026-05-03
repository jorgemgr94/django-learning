import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("conectapelu2")
# Lee config desde Django settings con prefijo CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")
# Auto-descubre tasks en INSTALLED_APPS
app.autodiscover_tasks()
