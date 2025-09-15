import os
from celery import Celery

# set default Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automation_project.settings")

app = Celery("automation_project")

# load settings with `CELERY_` namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# discover tasks inside all apps
app.autodiscover_tasks()
