from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = False

# Only force HTTPS once you actually have TLS terminated somewhere (nginx,
# Caddy, Cloudflare) in front of this app — until then, leave
# SECURE_SSL_REDIRECT=False in your .env or every request 404s/redirect-loops.
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# S3 / Cloudflare R2 for media storage — opt-in. Without these set, media
# files are stored on local disk (MEDIA_ROOT, already a persistent Docker
# volume) which is perfectly fine for a single-server deploy; switch to S3
# once you need multi-server/CDN-backed media.
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
if AWS_ACCESS_KEY_ID:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default=None)
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_DEFAULT_ACL = None

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
