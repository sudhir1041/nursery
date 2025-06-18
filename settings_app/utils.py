from django.core.mail import get_connection
from .models import Credential


def get_setting(key, default=None):
    try:
        return Credential.objects.get(key=key).value
    except Credential.DoesNotExist:
        return default


def get_email_connection():
    host = get_setting('EMAIL_HOST')
    user = get_setting('EMAIL_HOST_USER')
    password = get_setting('EMAIL_HOST_PASSWORD')
    port = get_setting('EMAIL_PORT')
    use_tls = get_setting('EMAIL_USE_TLS', 'True')
    if host and user and password:
        return get_connection(
            host=host,
            port=int(port or 587),
            username=user,
            password=password,
            use_tls=(str(use_tls).lower() == 'true'),
        )
    return None
