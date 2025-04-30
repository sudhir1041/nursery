"""
ASGI config for nurseryproject project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from dotenv import load_dotenv 
load_dotenv()  

from django.core.asgi import get_asgi_application

# TODO: Change 'nurseryproject.settings' if your settings file is different
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nurseryproject.settings')

application = get_asgi_application()

# --- Optional: Add Channels routing here if using WebSockets ---
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# import whatsapp_app.routing # Assuming you create routing.py in whatsapp_app
#
# application = ProtocolTypeRouter({
#   "http": get_asgi_application(),
#   "websocket": AuthMiddlewareStack(
#         URLRouter(
#             whatsapp_app.routing.websocket_urlpatterns # Define your WebSocket paths here
#         )
#     ),
# })
