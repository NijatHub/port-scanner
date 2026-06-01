"""
Celery application instance for the portscanner project.

Usage:
    celery -A portscanner worker -l info
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portscanner.settings")

app = Celery("portscanner")

# Pull CELERY_* settings from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()
