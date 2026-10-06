"""Ligacao dos models aos avisos: salvou ou apagou, e o evento esta ligado, agenda um aviso.

A configuracao e conferida aqui (uma consulta pequena) para nao encher a fila do
Celery com aviso desligado; a tarefa confere de novo quando roda.
"""

from django.db.models.signals import post_delete, post_save

from apps.notificacoes import agenda, eventos


def _ligado(conta_id, evento):
    from apps.notificacoes.models import ConfiguracaoNotificacao

    configuracao = ConfiguracaoNotificacao.all_objects.filter(account_id=conta_id).only(
        "ligado", "regras").first()
    return configuracao is not None and (
        configuracao.canal(evento, "navegador") or configuracao.canal(evento, "email"))


def enfileirar(conta_id, aviso):
    from apps.core.tarefas import enfileirar as para_fila
    from apps.notificacoes.tasks import notificar

    para_fila(notificar, str(conta_id), aviso)


def _registrar(obj, acao):
    evento = eventos.evento_de(type(obj), acao)
    if evento is None or not obj.account_id or not _ligado(obj.account_id, evento):
        return
    agenda.agendar(obj.account_id, obj._meta.label_lower, obj.pk, eventos.aviso(obj, acao),
                   enfileirar)


def salvou(sender, instance, created, raw=False, **kwargs):
    if not raw:  # loaddata: dado de fixture nao e evento
        _registrar(instance, "criado" if created else "alterado")


def apagou(sender, instance, **kwargs):
    _registrar(instance, "excluido")


def tarefa_terminou(execucao):
    """Chamado por apps/integracoes/tempo_real.publicar quando a tarefa grava o fim."""
    if _ligado(execucao.account_id, eventos.TAREFA_FALHOU):
        agenda.agendar(execucao.account_id, "integracoes.execucaointegracao", execucao.pk,
                       eventos.aviso_de_tarefa(execucao), enfileirar)


def conectar():
    for modelo in eventos.MODELOS:
        post_save.connect(salvou, sender=modelo, dispatch_uid=f"notificar_salvou_{modelo}")
        post_delete.connect(apagou, sender=modelo, dispatch_uid=f"notificar_apagou_{modelo}")
