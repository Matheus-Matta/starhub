"""Configuracao comum a dev e prod. O que muda entre ambientes fica em dev.py/prod.py."""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(nome, padrao=None):
    return os.environ.get(nome, padrao)


def env_lista(nome, padrao=""):
    return [item.strip() for item in env(nome, padrao).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-inseguro-nao-use-em-producao")
DEBUG = False
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    # daphne primeiro: assim o runserver sobe o servidor ASGI (HTTP + WebSocket).
    "daphne",
    # Substitui django.contrib.admin: mesmo admin, com o site e o tema do StarHub.
    "apps.core.admin_app.StarHubAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    # auditlog com o nome da secao em portugues (apps/core/auditoria.py).
    "apps.core.auditoria.AuditoriaConfig",
    "rest_framework",
    "rest_framework_simplejwt",
    "channels",
    "apps.core",
    "apps.loja",
    "apps.woo_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.tenant.middleware.TenantMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# O padrao do Django (DENY) impede ate o proprio site de mostrar o admin num
# iframe. O modal dos botoes "+"/lapis dos campos de relacao abre a pagina num
# iframe (static/starhub/js/modal-relacionado.js). SAMEORIGIN libera so o proprio
# site: outro dominio continua sem poder embutir o admin (protecao contra clickjacking).
X_FRAME_OPTIONS = "SAMEORIGIN"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # templates/ vem antes dos apps: e ele que sobrescreve os templates do admin.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            # Tags do tema ({% icone %}, {% componente %}...) sem {% load %} em todo template.
            "builtins": ["apps.core.templatetags.starhub"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = ["apps.core.tenant.auth_backend.AccessProfileBackend"]
LOGIN_URL = "admin:login"

AUDITLOG_INCLUDE_ALL_MODELS = True
AUDITLOG_STORE_JSON_CHANGES = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {"jwt_login": "20/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=int(env("JWT_ACESSO_DIAS", "7"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
}

CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Menu lateral do admin (apps/core/ui/menu.py). Cada app vira uma SECAO com
# separador; cada model e um item com o proprio icone (id do simbolo em
# static/starhub/img/icones.svg). Chave: "app_label.model_name".
STARHUB_MENU_ICONES = {
    "loja.produto": "package",
    "loja.categoria": "layout-list",
    "loja.cliente": "users-round",
    "loja.pedido": "clipboard-list",
    "loja.tag": "star",
    "loja.cupom": "wallet",
    "loja.tipovariante": "layout-grid",
    "loja.varianteproduto": "archive",
    "core.account": "house",
    "core.user": "user",
    "core.accessprofile": "shield",
    "core.address": "folder",
    "core.externalreference": "external-link",
    "core.saleschannel": "plug",
    "core.publicationpolicy": "sliders-horizontal",
    "core.publicationstate": "history",
    "woo_api.chaveapi": "key-round",
}
# Models de um app que aparecem na secao de outro: {"app_origem": "app_destino"}.
# As chaves da API Woo sao credencial de acesso da conta, entao ficam junto de
# contas, usuarios e perfis de acesso (app core).
STARHUB_MENU_AGRUPAR = {"woo_api": "core"}
# Paginas custom (sem model) no menu: {"app_label": [("Titulo", "admin:nome_url")]}.
STARHUB_MENU_PAGINAS = {}

