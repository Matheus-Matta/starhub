from celery import shared_task


@shared_task
def ping():
    """Confere a fila de ponta a ponta: `ping.delay().get()` precisa devolver "pong"."""
    return "pong"
