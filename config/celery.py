import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("starhub")
# Toda chave CELERY_* do settings vira configuracao do Celery.
app.config_from_object("django.conf:settings", namespace="CELERY")
# Procura tasks.py em cada app instalado (cada marketplace tem o seu).
app.autodiscover_tasks()
