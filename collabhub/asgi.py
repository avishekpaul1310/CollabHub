import os
import django
from django.core.asgi import get_asgi_application

# Check if we're running in production
is_prod = os.environ.get('COLLABHUB_ENVIRONMENT') == 'production'

# Use production settings if the COLLABHUB_ENVIRONMENT variable is set to 'production'
if is_prod:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collabhub.settings_prod')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collabhub.settings')

# Set up Django before importing any app modules
django.setup()

# Now it's safe to import application modules
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
import workspace.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                workspace.routing.websocket_urlpatterns
            )
        )
    ),
})