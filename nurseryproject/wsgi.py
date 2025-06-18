"""
WSGI config for nurseryproject project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nurseryproject.settings')

application = get_wsgi_application()
