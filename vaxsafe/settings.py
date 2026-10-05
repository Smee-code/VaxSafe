"""Django settings for VaxSafe, an animal bite treatment center management system."""
import os
from pathlib import Path

from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """Read KEY=value lines from a .env file into the environment (real environment variables win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / '.env')


def _env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# Production is the default: debug mode must be switched on explicitly.
DEBUG = os.environ.get('VAXSAFE_DEBUG', '0') == '1'

_DEV_SECRET_KEY = 'django-insecure-vaxsafe-local-development-only'
SECRET_KEY = os.environ.get('VAXSAFE_SECRET_KEY', _DEV_SECRET_KEY if DEBUG else '')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'VAXSAFE_SECRET_KEY is not set. Add it to the .env file (see .env.example), '
        'or set VAXSAFE_DEBUG=1 for local development.'
    )

ALLOWED_HOSTS = _env_list('VAXSAFE_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = [
    f'https://*{host}' if host.startswith('.') else f'https://{host}'
    for host in ALLOWED_HOSTS if host not in ('localhost', '127.0.0.1', '*')
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'accounts',
    'core',
    'clinic',
    'inventory',
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.CurrentRequestMiddleware',
    'core.middleware.ModalRedirectMiddleware',
]

ROOT_URLCONF = 'vaxsafe.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.vaxsafe',
            ],
        },
    },
]

WSGI_APPLICATION = 'vaxsafe.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Sessions end when the browser closes, or after 8 hours (one shift).
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MESSAGE_TAGS = {message_constants.ERROR: 'danger'}

# Production hardening -------------------------------------------------------
# PythonAnywhere (and most hosts) terminate HTTPS in front of Django and say so
# in this header. Turn on "Force HTTPS" in the PythonAnywhere Web tab to
# redirect plain HTTP; Django then only needs to mark cookies as HTTPS-only.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = os.environ.get('VAXSAFE_SECURE_COOKIES', '1') == '1'
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SESSION_COOKIE_HTTPONLY = True
    SECURE_SSL_REDIRECT = os.environ.get('VAXSAFE_SSL_REDIRECT', '0') == '1'
    SECURE_HSTS_SECONDS = int(os.environ.get('VAXSAFE_HSTS_SECONDS', '0'))
    SECURE_REFERRER_POLICY = 'same-origin'

# The HTTPS redirect is handled by the host ("Force HTTPS"), and HSTS is opt-in
# through VAXSAFE_HSTS_SECONDS once HTTPS is confirmed working.
SILENCED_SYSTEM_CHECKS = ['security.W004', 'security.W008']

# Send unexpected errors to the server log (PythonAnywhere: the "Error log" link on the Web tab).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
}
