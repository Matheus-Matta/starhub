from celery import shared_task


@shared_task
def ping():
    """Confere a fila de ponta a ponta: `ping.delay().get()` precisa devolver "pong"."""
    return "pong"


@shared_task
def exportar_relatorio(execucao_id):
    from apps.core.relatorios.tarefa import executar

    return executar(execucao_id)
