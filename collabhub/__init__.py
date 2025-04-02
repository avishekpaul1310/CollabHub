# Import the celery app
from .celery import app as celery_app

# Make the app available at module level
__all__ = ('celery_app',)
