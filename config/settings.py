import os
from pathlib import Path

import pymysql

pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-secret-key")
DEBUG = env("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = [item.strip() for item in env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if item.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.exams",
    "apps.judge",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

db_engine = env("DJANGO_DB_ENGINE", "sqlite").lower()
if db_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DJANGO_DB_NAME", "online_exam"),
            "USER": env("DJANGO_DB_USER", "root"),
            "PASSWORD": env("DJANGO_DB_PASSWORD", ""),
            "HOST": env("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": env("DJANGO_DB_PORT", "3306"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / env("DJANGO_DB_NAME", "db.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")

SESSION_ENGINE = "django.contrib.sessions.backends.db"

redis_cache_url = env("REDIS_CACHE_URL", "")
if redis_cache_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": redis_cache_url,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "online-exam-local-cache",
        }
    }

PASSWORD_RESET_CODE_TTL = int(env("PASSWORD_RESET_CODE_TTL", "600"))
PASSWORD_RESET_CODE_MAX_ATTEMPTS = int(env("PASSWORD_RESET_CODE_MAX_ATTEMPTS", "5"))

JUDGE_EXECUTION_MODE = env("JUDGE_EXECUTION_MODE", "local")
JUDGE_PYTHON_COMMAND = env("JUDGE_PYTHON_COMMAND", "python")
JUDGE_TIMEOUT_SECONDS = int(env("JUDGE_TIMEOUT_SECONDS", "2"))
JUDGE_MAX_OUTPUT_CHARS = int(env("JUDGE_MAX_OUTPUT_CHARS", "2000"))
JUDGE_TEMP_DIR = BASE_DIR / env("JUDGE_TEMP_DIR", ".judge_tmp")
JUDGE_DOCKER_COMMAND = env("JUDGE_DOCKER_COMMAND", "docker")
JUDGE_DOCKER_IMAGE = env("JUDGE_DOCKER_IMAGE", "python:3.13-slim")
JUDGE_DOCKER_MEMORY_LIMIT = env("JUDGE_DOCKER_MEMORY_LIMIT", "128m")
JUDGE_DOCKER_CPU_LIMIT = env("JUDGE_DOCKER_CPU_LIMIT", "0.5")
JUDGE_DOCKER_EXTRA_TIMEOUT_SECONDS = int(env("JUDGE_DOCKER_EXTRA_TIMEOUT_SECONDS", "5"))

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(env("EMAIL_PORT", "465"))
EMAIL_USE_SSL = env("EMAIL_USE_SSL", "True").lower() == "true"
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "20"))

SILICONFLOW_API_KEY = env("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_MODEL = env("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
SILICONFLOW_TIMEOUT = int(env("SILICONFLOW_TIMEOUT", "60"))
