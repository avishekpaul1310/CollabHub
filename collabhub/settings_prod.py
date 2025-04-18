"""
Production settings for collabhub project for Google Cloud deployment.
This file imports from settings.py but overrides settings for production use.
"""
import os
import environ
from .settings import *  # Import everything from the original settings

# Initialize environment variables
env = environ.Env()

# Read .env file if it exists
env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_file):
    env.read_env(env_file)

# Override settings for production
DEBUG = env.bool('DEBUG', default=False)
SECRET_KEY = env('SECRET_KEY', default=SECRET_KEY)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

# Database - use PostgreSQL for production
if env('DATABASE_URL', default=None):
    DATABASES = {
        'default': env.db(),  # Parses DATABASE_URL
    }

# Redis-based channel layer for WebSockets
if env('REDIS_URL', default=None):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [env('REDIS_URL')],
            },
        }
    }

# Celery settings
if env('REDIS_URL', default=None):
    CELERY_BROKER_URL = env('REDIS_URL')
    CELERY_RESULT_BACKEND = env('REDIS_URL')

# Static and media files
if env.bool('USE_GCS', default=False):
    # Use Google Cloud Storage
    GS_BUCKET_NAME = env('GS_BUCKET_NAME', default=None)
    if GS_BUCKET_NAME:
        # Add Google Cloud Storage libraries to INSTALLED_APPS
        INSTALLED_APPS += ['storages']
        
        # GCS settings
        GS_CREDENTIALS = env('GS_CREDENTIALS', default=None)
        GS_DEFAULT_ACL = 'publicRead'
        
        # Use GCS for media files
        DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
        
        # Optionally use GCS for static files too
        if env.bool('GCS_STATIC', default=False):
            STATICFILES_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
    
# Add logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': env('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
        'workspace': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True