"""
WSGI config for collabhub project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Check if we're running in production
is_prod = os.environ.get('COLLABHUB_ENVIRONMENT') == 'production'

# Use production settings if the COLLABHUB_ENVIRONMENT variable is set to 'production'
if is_prod:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collabhub.settings_prod')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collabhub.settings')

application = get_wsgi_application()
