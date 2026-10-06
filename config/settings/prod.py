"""Prod (Docker): uvicorn (blue e green), worker e beat do Celery em containers separados,
Redis e PostgreSQL no compose (ou o banco de fora, por POSTGRES_HOST). Tudo que muda por
ambiente vem do .env (veja .env.example)."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env, env_lista

DEBUG = False


def obrigatoria(nome):
    valor = env(nome)
    if not valor:
        raise ImproperlyConfigured(f"Defina a variavel de ambiente {nome} (veja .env.example).")
    return valor


def ligado(nome, padrao="1"):
    return env(nome, padrao).strip().lower() in ("1", "true", "sim", "yes", "on")


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
        # Conexao reaproveitada entre requisicoes; 0 fecha a cada uma (pgbouncer).
        "CONN_MAX_AGE": int(env("POSTGRES_CONN_MAX_AGE", "60")),
        # Banco gerenciado (RDS, Supabase...) costuma exigir SSL: require.
        "OPTIONS": {"sslmode": env("POSTGRES_SSLMODE", "prefer")},
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
STARHUB_TAREFAS_EM_THREAD = False  # o worker e outro container: tarefa vai para o Redis

# Estaticos servidos pelo proprio app (uvicorn nao serve /static/): WhiteNoise logo
# depois do SecurityMiddleware, com gzip/brotli gerados no collectstatic da imagem.
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
# Media (fotos de avaliacao, imagens importadas) servida pelo app: a Shopify baixa as
# fotos pela URL do hub. Com proxy servindo /media/ (nginx), desligue.
SERVIR_MEDIA = ligado("SERVIR_MEDIA", "1")

# O TLS termina no proxy; ele avisa por este cabecalho que a conexao era HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Desligue so para testar sem HTTPS na frente (ex.: http://ip:8000 na rede interna).
SECURE_SSL_REDIRECT = ligado("DJANGO_SSL_REDIRECT", "1")
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if SECURE_SSL_REDIRECT else 0
SECURE_CONTENT_TYPE_NOSNIFF = True

# CORS: so os dominios do .env e so nas rotas de CORS_URLS_REGEX (padrao: avaliacoes do
# tema da loja). AVALIACOES_ORIGENS e o nome antigo e continua valendo.
CORS_ALLOWED_ORIGINS = [*env_lista("CORS_ALLOWED_ORIGINS"), *env_lista("AVALIACOES_ORIGENS")]
if CORS_ALLOWED_ORIGINS:
    INSTALLED_APPS = [*INSTALLED_APPS, "corsheaders"]  # noqa: F405
    MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware", *MIDDLEWARE]
    CORS_URLS_REGEX = env("CORS_URLS_REGEX", r"^/integracoes/shopify/avaliacoes/")

# Tudo para a saida padrao: o Docker guarda (docker compose logs). Sem isto o Django em
# DEBUG=False mandaria os erros so para e-mail, que nao esta configurado.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"padrao": {"format": "{asctime} {levelname} {name}: {message}",
                              "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "padrao"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"),
                           "propagate": False}},
}
