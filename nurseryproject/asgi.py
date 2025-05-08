import os
import django 
from django.core.asgi import get_asgi_application
# Import Channels routing and middleware AFTER django.setup()
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Set the default Django settings module first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nurseryproject.settings')

# --- IMPORTANT: Call django.setup() here ---
django.setup()
# ---------------------------------------------

# Now import things that might depend on Django apps being ready
import whatsapp_app.routing 

# Get the standard Django ASGI application AFTER setup
django_asgi_app = get_asgi_application()

# Define the ASGI application routing
application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": django_asgi_app,

    # WebSocket handler
    "websocket": AuthMiddlewareStack( 
        URLRouter(
            whatsapp_app.routing.websocket_urlpatterns
        )
    ),
})

