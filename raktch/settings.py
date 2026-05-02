"""
Django settings for raktch project.
All runtime configuration is read from the root .env file via python-decouple.
"""

from pathlib import Path
from datetime import timedelta

# ---------------------------------------------------------------------------
# Configure python-decouple to read from the repo root .env
# (one level above backend/)
# ---------------------------------------------------------------------------
from decouple import AutoConfig
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # repo root
config = AutoConfig(search_path=str(_ROOT_DIR))

from decouple import Csv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Root of the whole repo (one level above backend/)
ROOT_DIR = BASE_DIR.parent

# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------
SECRET_KEY = config('DJANGO_SECRET_KEY', default='insecure-default-change-me')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config(
    'DJANGO_ALLOWED_HOSTS',
    default='localhost,127.0.0.1,.vercel.app',
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-ins — use custom configs to override AutoField for MongoDB
    'raktch.mongocompat.MongoAdminConfig',
    'raktch.mongocompat.MongoAuthConfig',
    'raktch.mongocompat.MongoContentTypesConfig',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',

    # Project apps
    'accounts',
    'rbac',
    'people',
    'org',
    'projects',
    'modules',
    'tasks',
    'workitems',
    'boards',
    'planning',
    'deployments',
    'notifications',
    'searchapp',
    'dashboards',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'raktch.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'raktch.wsgi.application'

# ---------------------------------------------------------------------------
# Database — MongoDB Atlas via django-mongodb-backend
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django_mongodb_backend',
        'HOST': config('MONGODB_URI'),
        'NAME': config('MONGODB_NAME', default='raktchops'),
    }
}

# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static and media
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MEDIA_URL = config('MEDIA_URL', default='/media/')
MEDIA_ROOT = ROOT_DIR / config('MEDIA_ROOT', default='backend/media')

DEFAULT_AUTO_FIELD = 'django_mongodb_backend.fields.ObjectIdAutoField'

# ---------------------------------------------------------------------------
# MongoDB-compatible migrations for Django built-in apps
# ---------------------------------------------------------------------------
MIGRATION_MODULES = {
    'admin': 'mongo_migrations.admin',
    'auth': 'mongo_migrations.auth',
    'contenttypes': 'mongo_migrations.contenttypes',
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    'DJANGO_CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = config(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    default='http://localhost:3000',
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': config('DEFAULT_PAGE_SIZE', default=20, cast=int),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'raktch.exception_handler.custom_exception_handler',
}

# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=config('AUTH_JWT_ACCESS_MINUTES', default=60, cast=int)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=config('AUTH_JWT_REFRESH_DAYS', default=7, cast=int)
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=1025, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@raktch.com')

# ---------------------------------------------------------------------------
# Onboarding / domain validation
# ---------------------------------------------------------------------------
ALLOWED_DOMAINS = config('AUTH_ALLOWED_EMAIL_DOMAINS', default='raktch.com', cast=Csv())
AUTH_REQUIRE_APPROVAL = config('AUTH_REQUIRE_APPROVAL', default=True, cast=bool)
AUTH_DEFAULT_ROLE = config('AUTH_DEFAULT_ROLE', default='staff')
AUTH_INVITE_EXPIRY_HOURS = config('AUTH_INVITE_EXPIRY_HOURS', default=72, cast=int)
AUTH_EMAIL_VERIFICATION_EXPIRY_HOURS = config('AUTH_EMAIL_VERIFICATION_EXPIRY_HOURS', default=24, cast=int)
AUTH_PASSWORD_RESET_EXPIRY_MINUTES = config('AUTH_PASSWORD_RESET_EXPIRY_MINUTES', default=30, cast=int)
AUTH_LOGIN_RATE_LIMIT = config('AUTH_LOGIN_RATE_LIMIT', default=5, cast=int)
AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS = config('AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS', default=300, cast=int)
AUTH_LOCKOUT_MINUTES = config('AUTH_LOCKOUT_MINUTES', default=15, cast=int)

# Frontend URLs used in email links
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')
PASSWORD_RESET_URL = config('DJANGO_PASSWORD_RESET_URL', default='http://localhost:3000/reset-password')
EMAIL_VERIFICATION_URL = config('DJANGO_EMAIL_VERIFICATION_URL', default='http://localhost:3000/verify-email')

# ---------------------------------------------------------------------------
# Repository validation
# ---------------------------------------------------------------------------
REPOSITORY_ALLOWED_HOSTS = config('REPOSITORY_ALLOWED_HOSTS', default='github.com,www.github.com', cast=Csv())
REPOSITORY_REQUIRE_HTTPS = config('REPOSITORY_REQUIRE_HTTPS', default=True, cast=bool)

# ---------------------------------------------------------------------------
# Deployment tracking
# ---------------------------------------------------------------------------
DEPLOYMENT_APPROVAL_REQUIRED_FOR = config(
    'DEPLOYMENT_APPROVAL_REQUIRED_FOR',
    default='staging,uat,production',
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Search and pagination
# ---------------------------------------------------------------------------
MAX_PAGE_SIZE = config('MAX_PAGE_SIZE', default=100, cast=int)
SEARCH_MIN_QUERY_LENGTH = config('SEARCH_MIN_QUERY_LENGTH', default=2, cast=int)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = config('LOG_LEVEL', default='INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
}
