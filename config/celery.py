import os

from celery import Celery
from celery.signals import beat_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("starhub")
# Toda chave CELERY_* do settings vira configuracao do Celery.
app.config_from_object("django.conf:settings", namespace="CELERY")
# Procura tasks.py em cada app instalado (cada marketplace tem o seu).
app.autodiscover_tasks()


@beat_init.connect
def conferir_ao_subir(**_):
    # O beat so roda a agenda 30 min depois de subir; o sistema pode ter ficado fora.
    # A janela comeca onde a ultima conferencia parou, entao esta ja cobre o tempo parado.
    app.send_task("apps.integracoes.conferencia.conferir_pedidos_das_lojas")
