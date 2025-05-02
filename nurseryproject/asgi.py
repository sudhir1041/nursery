import os
from django.core.asgi import get_asgi_application
# Import Channels routing and middleware
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack # Handles Django auth over WebSockets
# Import your app's routing configuration
import whatsapp_app.routing

# Set the default Django settings module for the 'asgi' application.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nurseryproject.settings')

# Get the standard Django ASGI application to handle traditional HTTP requests first.
django_asgi_app = get_asgi_application()

# Define the ASGI application routing
application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": django_asgi_app,

    # WebSocket handler
    "websocket": AuthMiddlewareStack( # Handles user authentication
        URLRouter(
            # Point to your app's WebSocket URL patterns
            whatsapp_app.routing.websocket_urlpatterns
        )
    ),
})
