import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collabhub.settings')

app = Celery('collabhub')

# Use a string here to avoid namespace issues
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

# Configure the periodic tasks
app.conf.beat_schedule = {
    'deliver-slow-channel-messages-every-5-minutes': {
        'task': 'workspace.tasks.deliver_slow_channel_messages',
        'schedule': 300.0,  # Every 5 minutes
    },
}