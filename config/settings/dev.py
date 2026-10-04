"""Dev: um terminal so. `python manage.py runserver` sobe HTTP + WebSocket (daphne)
e as tarefas do Celery rodam na hora, dentro do proprio processo, sem Redis."""

from .base import *  # noqa: F403

DEBUG = True

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
# Sem isso uma tarefa que quebra em dev some em silencio; com isso o erro sobe.
CELERY_TASK_EAGER_PROPAGATES = True
# Eager nao grava o SUCCESS no backend sem isto: a barra de progresso (celery_progress)
# ficaria parada no ultimo passo em vez de ver a tarefa terminar.
CELERY_TASK_STORE_EAGER_RESULT = True
# Eager roda a tarefa DENTRO da requisicao: a sincronizacao da Shopify prendia o POST
# do admin ate o Daphne matar, e o webhook respondia depois da Shopify desistir. Com
# isto apps.core.tarefas.enfileirar roda as tarefas longas numa thread. Os testes
# desligam (conftest.py raiz) para ler o resultado da tarefa logo depois da chamada.
STARHUB_TAREFAS_EM_THREAD = True
# Com a tarefa na thread, duas conexoes escrevem no SQLite ao mesmo tempo. timeout:
# espera o lock em vez de "database is locked" na hora. IMMEDIATE: a transacao pega
# o lock de escrita no BEGIN; a DEFERRED que le e depois escreve falha sem esperar.
DATABASES = {
    "default": {
        **DATABASES["default"],  # noqa: F405
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}

# Dev aberto para testar integracao de qualquer lugar (tunel do VS Code, ngrok,
# IP da rede local, front em outra porta). NUNCA copie isto para o prod.py: la
# o host vem de DJANGO_ALLOWED_HOSTS e o CORS nao existe.
ALLOWED_HOSTS = ["*"]

# CORS: qualquer origem pode chamar a API pelo navegador. Com credenciais, o
# django-cors-headers devolve a propria origem (e nao "*"), que o navegador exige.
INSTALLED_APPS = [*INSTALLED_APPS, "corsheaders"]  # noqa: F405
# Primeiro da lista: responde o preflight (OPTIONS) antes de autenticacao e CSRF.
MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware", *MIDDLEWARE]  # noqa: F405
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
# Cabecalhos de paginacao do Woo: sem isto o JS do navegador nao consegue le-los.
CORS_EXPOSE_HEADERS = ["X-WP-Total", "X-WP-TotalPages", "Link"]

# Login no admin pelo tunel (o form do admin tem CSRF e o tunel e https). O CSRF
# nao aceita "*": cada dominio de fora que abrir o admin precisa entrar aqui.
CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, "https://*.devtunnels.ms"]  # noqa: F405
