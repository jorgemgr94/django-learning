import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("conectapelu2")
# Read config from Django settings with CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")
# Auto-discover tasks in INSTALLED_APPS
app.autodiscover_tasks()
