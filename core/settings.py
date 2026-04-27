import os
from pathlib import Path

import dotenv
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

dotenv.load_dotenv(BASE_DIR / ".env")

# ===== Secrets =====

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT != "production"

SERVICE_ID = os.environ.get("SERVICE_ID", "test-service")
SERVICE_SECRET = os.environ.get("SERVICE_SECRET", "")

HOST = os.environ.get("HOST", "127.0.0.1:8000")
SELF_URL = f"http{'' if DEBUG else 's'}://{HOST}"

ALLOWED_HOSTS = ["*"]

cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = cors_env.split(",") if cors_env else ["http://127.0.0.1:8000"]

# ===== Installed Apps =====

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "api.apps.ApiConfig",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
]

# ===== Middleware =====

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "utils.i18n_middleware.I18nMiddleware",
]

# ===== Application =====

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

# ===== Templates =====

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

# ===== DRF =====

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "utils.renderers.CamelCaseJSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "utils.parsers.CamelCaseJSONParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "utils.exception_handler.exception_handler",
}

# ===== DRF Spectacular =====

SPECTACULAR_SETTINGS = {
    "TITLE": SERVICE_ID.replace("-service", "").title() + " API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": True,
}

# ===== Databases =====

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ===== Caches =====

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# ===== Static / Media =====

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

PUBLIC_URL = "/public/"
PUBLIC_ROOT = BASE_DIR / "public"

# ===== Security =====

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_PROXY_SSL_HEADER: tuple[str, str] | None = None
SECURE_SSL_REDIRECT = False

if ENVIRONMENT == "production":
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )
    SECURE_SSL_REDIRECT = True

# ===== CORS =====

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    "cache-control",
    "pragma",
    "expires",
]

# ===== Misc =====

LANGUAGE_CODE = "en-us"
SUPPORTED_LANGUAGES = ("en", "ru", "ro")
DEFAULT_LANGUAGE = "en"

TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
