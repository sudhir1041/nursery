# nurseryproject/celery.py
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
# TODO: Ensure 'nurseryproject.settings' matches your project's settings file.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nurseryproject.settings')

# Create the Celery application instance
# TODO: Change 'nurseryproject' if your project directory name is different
app = Celery('nurseryproject')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix in settings.py.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
# This automatically discovers tasks defined in tasks.py files in your apps.
app.autodiscover_tasks()

# Optional: Example debug task
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """A sample task for debugging purposes."""
    print(f'Request: {self.request!r}')

