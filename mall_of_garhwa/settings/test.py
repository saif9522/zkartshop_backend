from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

# Fast, insecure hasher — real security doesn't matter for test-only accounts,
# and this is the single biggest speedup for a Django test suite.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Run Celery tasks synchronously, in-process — no Redis/worker needed to test
# the code paths that call .delay().
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Don't throttle test requests (the real OTP/login rate limits would make
# a test hitting the same endpoint repeatedly fail for the wrong reason).
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405

# Never hit real third-party APIs from tests — keep the keys empty so every
# service function takes its already-tested "not configured" fallback path.
APITXT_API_KEY = ""
RAZORPAY_KEY_ID = ""
RAZORPAY_KEY_SECRET = ""
ANTHROPIC_API_KEY = ""
GOOGLE_MAPS_API_KEY = ""
VAPID_PRIVATE_KEY_PEM = ""
FACEBOOK_PAGE_ACCESS_TOKEN = ""
