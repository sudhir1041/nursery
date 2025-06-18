import os
from pathlib import Path
import pymysql
pymysql.install_as_MySQLdb()
from django.utils import timezone
from dotenv import load_dotenv
from django.conf import settings

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# --- Load Environment Variables ---
load_dotenv(BASE_DIR / '.env')

# --- Encryption Key for Settings App ---
from cryptography.fernet import Fernet
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY')
if not FIELD_ENCRYPTION_KEY:
    FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()

# --- Base URL for constructing webhook endpoints ---
BASE_WEBHOOK_URL = os.getenv('BASE_WEBHOOK_URL', '')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-fallback-key-for-dev')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True


ALLOWED_HOSTS = [
    'admin.nurserynisarga.in',
    '127.0.0.1:8000',
]

CSRF_TRUSTED_ORIGINS = [
    'https://admin.nurserynisarga.in',
    'http://127.0.0.1:8000',
]


LOGIN_URL = '/accounts/login/' 
LOGIN_REDIRECT_URL = '/' 
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Application definition
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'django_celery_beat',
    'invoice_app',
    'woocommerce_app',
    'shopify_app',
    'facebook_app',
    'whatsapp_app',
    'shipment_app',
    'settings_app',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nurseryproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'nurseryproject.wsgi.application'

# --- WooCommerce Settings ---
WOOCOMMERCE_STORE_URL = os.getenv('WOOCOMMERCE_STORE_URL')
WOOCOMMERCE_CONSUMER_KEY = os.getenv('WOOCOMMERCE_CONSUMER_KEY')
WOOCOMMERCE_CONSUMER_SECRET = os.getenv('WOOCOMMERCE_CONSUMER_SECRET')
WOOCOMMERCE_WEBHOOK_SECRET = os.getenv('WOOCOMMERCE_WEBHOOK_SECRET', 'a-very-strong-random-secret')

# --- Shopify Settings ---
SHOPIFY_STORE_DOMAIN = os.getenv('SHOPIFY_STORE_DOMAIN')
SHOPIFY_API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2024-04')
SHOPIFY_ADMIN_ACCESS_TOKEN = os.getenv('SHOPIFY_ADMIN_ACCESS_TOKEN')
SHOPIFY_API_KEY = os.getenv('SHOPIFY_API_KEY')
SHOPIFY_API_SECRET_KEY = os.getenv('SHOPIFY_API_SECRET_KEY')
SHOPIFY_WEBHOOK_SECRET = os.getenv('SHOPIFY_WEBHOOK_SECRET', 'SHOPIFY_API_SECRET_KEY')

# --- whatsapp Settings ---
WHATSAPP_ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
WHATSAPP_PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
WHATSAPP_VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')
WHATSAPP_APP_SECRET = os.getenv('WHATSAPP_APP_SECRET')

# --- Construct full webhook URLs for reference ---
WHATSAPP_WEBHOOK_ENDPOINT = '/whatsapp/webhook/'
SHOPIFY_WEBHOOK_ENDPOINT = '/shopify/webhooks/receive-shopify-e5d4f3c2b1/'
WOOCOMMERCE_WEBHOOK_ENDPOINT = '/woocommerce/webhooks/orders/receive-9a8b7c6d5e/'

if BASE_WEBHOOK_URL:
    WHATSAPP_WEBHOOK_URL = f"{BASE_WEBHOOK_URL.rstrip('/')}{WHATSAPP_WEBHOOK_ENDPOINT}"
    SHOPIFY_WEBHOOK_URL = f"{BASE_WEBHOOK_URL.rstrip('/')}{SHOPIFY_WEBHOOK_ENDPOINT}"
    WOOCOMMERCE_WEBHOOK_URL = f"{BASE_WEBHOOK_URL.rstrip('/')}{WOOCOMMERCE_WEBHOOK_ENDPOINT}"
else:
    WHATSAPP_WEBHOOK_URL = WHATSAPP_WEBHOOK_ENDPOINT
    SHOPIFY_WEBHOOK_URL = SHOPIFY_WEBHOOK_ENDPOINT
    WOOCOMMERCE_WEBHOOK_URL = WOOCOMMERCE_WEBHOOK_ENDPOINT




# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'nursery'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        }
    }
}
# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/staticfiles/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Optional but helpful
# STATICFILES_DIRS = [
#     os.path.join(BASE_DIR, 'static'),
# ]

#Dynamic files and documents
MEDIA_ROOT = os.path.join(BASE_DIR, 'uploads')
MEDIA_URL = '/uploads/'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Define LOGS_DIR ---
LOGS_DIR = BASE_DIR / 'logs'
if not LOGS_DIR.exists():
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Warning: Could not create logs directory {LOGS_DIR}. Error: {e}")

# --- LOGGING Configuration ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': { 
            'format': '{levelname} {asctime} {module}: {message}',
            'style': '{',
        },
        'celery_format': {
            'format': '{levelname} {asctime} {task_name} {task_id} {module}: {message}',
            'style': '{',
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'app_file': { 
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'application.log',  
            'maxBytes': 1024 * 1024 * 10,  
            'backupCount': 5,
            'formatter': 'verbose', 
        },
        'shopify_file': { 
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'shopify.log', 
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 3,
            'formatter': 'verbose',
        },
        'celery_task_file': { 
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'celery_tasks.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'celery_format',
        },
    },
    'root': {
        'handlers': ['console', 'app_file'], 
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'app_file'], 
            'level': 'INFO',
            'propagate': True, 
        },
        'woocommerce_app': {
            'handlers': ['console', 'app_file'], 
            'level': 'INFO',
            'propagate': False, 
        },
        'shopify_app': { 
            'handlers': ['console', 'shopify_file'], 
            'level': 'INFO',
            'propagate': False,
        },
        'celery': { 
            'handlers': ['console', 'celery_task_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': { 
            'handlers': ['console', 'celery_task_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Example for handling database query logs (can be verbose)
        # 'django.db.backends': {
        #     'handlers': ['console'],
        #     'level': 'DEBUG' if DEBUG else 'WARNING', # Only show SQL in DEBUG
        #     'propagate': False,
        # },
    },
}

REDIS_HOST = "127.0.0.1"
REDIS_PORT = "6379"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}

# Celery Configuration (Example)
CELERY_BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/0' 
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}/1' 
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kolkata'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
