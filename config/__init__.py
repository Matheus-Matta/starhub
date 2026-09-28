# Garante que o app do Celery carregue junto com o Django, para o @shared_task
# dos apps se ligar a ele.
from .celery import app as celery_app

__all__ = ("celery_app",)
