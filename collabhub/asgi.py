import os
import django
from django.core.asgi import get_asgi_application

# Configure Django settings first
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