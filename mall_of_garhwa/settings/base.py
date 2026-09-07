"""
Base settings shared by every environment.
Environment-specific overrides live in development.py / production.py.
"""
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY")

# Used to encrypt sensitive PII at rest (Aadhaar/PAN/bank account numbers —
# see apps/core/encrypted_fields.py). Falls back to SECRET_KEY if unset so
# local dev never blocks on this, but set a dedicated key in production:
# rotating SECRET_KEY (e.g. after a leak) would otherwise also silently
# break decryption of every already-stored encrypted field.
FIELD_ENCRYPTION_KEY = config("FIELD_ENCRYPTION_KEY", default="")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "phonenumber_field",
    "channels",
    "drf_yasg",
]
ALLOWED_HOSTS = [
    'zkart.shop',
    'www.zkart.shop',
    'localhost',
    '127.0.0.1',
    '.onrender.com',  # Render default domain ke liye
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # <--- yeh line add karein
    # baaki saare middlewares...
]

CSRF_TRUSTED_ORIGINS = [
    'https://zkart.shop',
    'https://www.zkart.shop',
    'https://zkartshop-backend.onrender.com',
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.superadmin",
    "apps.vendors",
    "apps.catalog",
    "apps.cart",
    "apps.orders",
    "apps.delivery",
    "apps.adminpanel",
    "apps.notifications",
    "apps.inventory",
    "apps.reports",
    "apps.marketing",
    "apps.cms",
    "apps.wallet",
    "apps.chatbot",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mall_of_garhwa.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mall_of_garhwa.wsgi.application"
ASGI_APPLICATION = "mall_of_garhwa.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Defaults to SQLite (zero setup — just run `python manage.py migrate`).
# To use PostgreSQL instead, set DB_ENGINE=postgresql in .env along with
# DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT.
# To use MySQL/MariaDB, set DB_ENGINE=mysql along with the same variables
# (defaults to port 3306). Requires `mysqlclient` — see requirements.txt.
_db_engine = config("DB_ENGINE", default="sqlite3")

if _db_engine == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }
elif _db_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="3306"),
            "OPTIONS": {
                # utf8mb4 so product names/descriptions in Hindi/Marathi/etc. store correctly
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / config("SQLITE_NAME", default="db.sqlite3"),
        }
    }

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# 10MB cap on any single upload — previously unbounded (Django's own default
# only governs when uploads move from memory to a temp file, not a hard limit).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "120/minute",
        "otp": "5/minute",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("ACCESS_TOKEN_LIFETIME_MIN", default=15, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# Swagger / OpenAPI docs (drf-yasg) — served at /swagger/ and /redoc/
# ---------------------------------------------------------------------------
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT auth. Paste: Bearer <your access token>",
        }
    },
    "USE_SESSION_AUTH": False,
    "PERSIST_AUTH": True,
    "DEFAULT_MODEL_RENDERING": "example",
}
REDOC_SETTINGS = {
    "LAZY_RENDERING": False,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())

# ---------------------------------------------------------------------------
# Channels (Redis backend for WebSockets — live order & GPS tracking)
# ---------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [{"address": REDIS_URL, "socket_connect_timeout": 2, "socket_timeout": 2}],
        },
    }
}

# ---------------------------------------------------------------------------
# Celery — background jobs (SMS/WhatsApp, order auto-cancel, inventory expiry,
# AI report generation). Uses the same Redis instance as the cache/Channels.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
# Retries: transient SMS/API failures shouldn't need manual intervention.
CELERY_TASK_DEFAULT_RETRY_DELAY = 10  # seconds
CELERY_TASK_MAX_RETRIES = 3
# Belt-and-braces: don't let a stuck task (e.g. hung HTTP call) block a worker forever.
CELERY_TASK_TIME_LIMIT = 60
CELERY_TASK_SOFT_TIME_LIMIT = 45

# Fail FAST if the broker (Redis) isn't reachable when a task is queued —
# without this, .delay() retries connecting with backoff for many seconds
# on every OTP send / order notification, which is why everything felt slow
# whenever Redis wasn't running. safe_delay() already catches the failure
# and continues gracefully — it just needs the failure to happen quickly.
CELERY_BROKER_CONNECTION_TIMEOUT = 0.5
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BROKER_CONNECTION_RETRY = False
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 0.5, "socket_timeout": 0.5}
# Nothing in this codebase ever calls .get()/AsyncResult on a task — these are
# all fire-and-forget (SMS, broadcasts, reports). Ignoring results means
# Celery never talks to the result backend at all, which is what actually
# caused the ~19s hang on every .delay() when Redis wasn't running (the
# result-backend reconnect has its own separate, slower retry policy).
CELERY_TASK_IGNORE_RESULT = True
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"socket_connect_timeout": 0.5, "socket_timeout": 0.5}

# ---------------------------------------------------------------------------
# Custom project settings
# ---------------------------------------------------------------------------
OTP_EXPIRY_MINUTES = config("OTP_EXPIRY_MINUTES", default=5, cast=int)

# APITxT — SMS / WhatsApp / Voice OTP provider (https://apitxt.com)
APITXT_API_KEY = config("APITXT_API_KEY", default="")
APITXT_SENDER_ID = config("APITXT_SENDER_ID", default="MALLGW")
APITXT_SEND_OTP_URL = "https://apitxt.com/api/sendOTP"
APITXT_SEND_SMS_URL = "https://apitxt.com/api/sendMsg"

# Delivery pricing (flat fee for now — per-vendor/distance-based pricing comes later)
DELIVERY_CHARGE = config("DELIVERY_CHARGE", default=25, cast=int)
FREE_DELIVERY_THRESHOLD = config("FREE_DELIVERY_THRESHOLD", default=299, cast=int)

# Minutes a vendor has to accept an order before it's auto-cancelled (Celery beat job)
ORDER_ACCEPT_TIMEOUT_MINUTES = config("ORDER_ACCEPT_TIMEOUT_MINUTES", default=5, cast=int)

# Flat payout to the delivery partner per completed delivery (distance-based pricing later)
DELIVERY_PARTNER_PAYOUT_PER_ORDER = config("DELIVERY_PARTNER_PAYOUT_PER_ORDER", default=20, cast=int)

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="zKart.shop <noreply@zkart.shop>")
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = 5

# Anthropic API — powers the daily AI sales summary
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
ANTHROPIC_MODEL = config("ANTHROPIC_MODEL", default="claude-sonnet-4-6")

# Web Push (VAPID) — run `python manage.py generate_vapid_keys` once to get these.
VAPID_PUBLIC_KEY = config("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY_PEM = config("VAPID_PRIVATE_KEY_PEM", default="").replace("\\n", "\n")
VAPID_ADMIN_EMAIL = config("VAPID_ADMIN_EMAIL", default="admin@zkart.shop")

# Publicly reachable base URL for this backend — needed to build absolute
# media URLs for Facebook/Instagram posts (Meta's servers fetch the image
# themselves, so a relative /media/... path won't work).
SITE_URL = config("SITE_URL", default="http://localhost:8000")

# Meta Graph API — Facebook Page posts + Instagram Business posts.
# Get these from https://developers.facebook.com (a Meta Business app with
# a Page connected, and an Instagram Business account linked to that Page).
FACEBOOK_PAGE_ACCESS_TOKEN = config("FACEBOOK_PAGE_ACCESS_TOKEN", default="")
FACEBOOK_PAGE_ID = config("FACEBOOK_PAGE_ID", default="")
INSTAGRAM_BUSINESS_ACCOUNT_ID = config("INSTAGRAM_BUSINESS_ACCOUNT_ID", default="")
META_GRAPH_API_VERSION = config("META_GRAPH_API_VERSION", default="v21.0")
GOOGLE_OAUTH_CLIENT_ID = config("GOOGLE_OAUTH_CLIENT_ID", default="")
RAZORPAY_KEY_ID = config("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = config("RAZORPAY_KEY_SECRET", default="")
GOOGLE_MAPS_API_KEY = config("GOOGLE_MAPS_API_KEY", default="")
