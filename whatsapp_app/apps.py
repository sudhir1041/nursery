# whatsapp_app/apps.py

from django.apps import AppConfig

class WhatsappAppConfig(AppConfig):
    """
    App configuration for the whatsapp_app.

    Sets the default auto field type and the app name.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'whatsapp_app'
    verbose_name = "WhatsApp Integration" # How it appears in the admin

    # Optional: Add ready method for signal registration or other setup tasks
    # def ready(self):
    #     # Import signals here to ensure they are registered
    #     # import whatsapp_app.signals
    #     pass
