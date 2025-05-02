    # nurseryproject/asgi.py (or your project's asgi.py)

    import os
    from django.core.asgi import get_asgi_application
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack # Handles Django auth over WebSockets
    # --- Import your app's routing ---
    import whatsapp_app.routing

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nurseryproject.settings')

    # Get the standard Django ASGI app first for HTTP requests
    django_asgi_app = get_asgi_application()

    application = ProtocolTypeRouter({
        # Django's ASGI application to handle traditional HTTP requests
        "http": django_asgi_app,

        # WebSocket handler
        "websocket": AuthMiddlewareStack( # Handles user authentication
            URLRouter(
                # --- Point to your app's WebSocket URL patterns ---
                whatsapp_app.routing.websocket_urlpatterns
            )
        ),
    })
    