import base64
import binascii
import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv('SECRET_KEY', 'insecure-dev-key')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_cleanup.apps.CleanupConfig',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AccountStatusMiddleware',
]

ROOT_URLCONF = 'univers_academy.urls'

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
                'core.context_processors.user_profile_context',
                'core.context_processors.clerk_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'univers_academy.wsgi.application'

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'core.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = os.getenv('TIME_ZONE', 'Africa/Brazzaville')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

PRIVATE_STORAGE_ROOT = BASE_DIR / 'media' / 'private'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' if not DEBUG else 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@univers-academy.com')

CSRF_TRUSTED_ORIGINS = ['http://localhost', 'http://127.0.0.1', 'http://localhost:8000']
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# Clerk authentication (Google + email/password)
# ---------------------------------------------------------------------------
CLERK_PUBLISHABLE_KEY = os.getenv('CLERK_PUBLISHABLE_KEY', '').strip()
CLERK_SECRET_KEY = os.getenv('CLERK_SECRET_KEY', '').strip()


def _clerk_frontend_api_from_key(publishable_key):
    """Extract the Frontend API host encoded in a Clerk publishable key."""
    try:
        encoded = publishable_key.split('_', 2)[2]
        padded = encoded + '=' * (-len(encoded) % 4)
        return base64.b64decode(padded).decode('utf-8').rstrip('$')
    except (IndexError, ValueError, binascii.Error, UnicodeDecodeError):
        return ''


CLERK_FRONTEND_API = (
    os.getenv('CLERK_FRONTEND_API', '').strip()
    or _clerk_frontend_api_from_key(CLERK_PUBLISHABLE_KEY)
)
CLERK_JS_VERSION = os.getenv('CLERK_JS_VERSION', '6')
CLERK_JS_URL = (
    f'https://{CLERK_FRONTEND_API}/npm/@clerk/clerk-js@{CLERK_JS_VERSION}'
    '/dist/clerk.browser.js'
    if CLERK_FRONTEND_API else ''
)
# Since Clerk JS v6 the prebuilt UI lives in a separate bundle. Without it,
# clerk.mountSignIn() raises "Clerk was not loaded with Ui components".
CLERK_UI_VERSION = os.getenv('CLERK_UI_VERSION', '1')
CLERK_UI_URL = (
    f'https://{CLERK_FRONTEND_API}/npm/@clerk/ui@{CLERK_UI_VERSION}'
    '/dist/ui.browser.js'
    if CLERK_FRONTEND_API else ''
)
CLERK_AUTHORIZED_PARTIES = [
    origin.strip()
    for origin in os.getenv(
        'CLERK_AUTHORIZED_PARTIES',
        'http://localhost:8000,http://127.0.0.1:8000',
    ).split(',')
    if origin.strip()
]
CLERK_ENABLED = bool(
    CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY and CLERK_FRONTEND_API
)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_SSL_REDIRECT = True

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
