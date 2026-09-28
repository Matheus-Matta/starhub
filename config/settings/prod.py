"""Prod: daphne, worker e beat do Celery em processos separados, Redis e PostgreSQL."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env

DEBUG = False


def obrigatoria(nome):
    valor = env(nome)
    if not valor:
        raise ImproperlyConfigured(f"Defina a variavel de ambiente {nome} (veja .env.example).")
    return valor


SECRET_KEY = obrigatoria("DJANGO_SECRET_KEY")
REDIS_URL = obrigatoria("REDIS_URL")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": obrigatoria("POSTGRES_DB"),
        "USER": obrigatoria("POSTGRES_USER"),
        "PASSWORD": obrigatoria("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
}
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# O TLS termina no proxy (nginx); ele avisa por este cabecalho que a conexao era HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_CONTENT_TYPE_NOSNIFF = True
