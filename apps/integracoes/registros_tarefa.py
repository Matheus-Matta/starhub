"""Liga a tarefa aos registros que ela tocou (TarefaRegistro), sem cada tarefa lembrar.

Todo log gravado dentro de uma tarefa ja leva o tarefa_id (apps/core/origem.py): o
post_save do LogEntry transforma isso numa linha de TarefaRegistro. Assim importacao,
webhook, sincronizacao e API Woo ficam ligadas aos produtos, variantes e pedidos que
alteraram sem mexer em nenhuma delas.

O envio para a loja pode nao alterar nada no hub: ele chama `vincular` direto.
"""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save

from apps.integracoes.modelos_registro import TarefaRegistro

logger = logging.getLogger(__name__)


def vincular(execucao_id, tipo_id, pk, descricao=""):
    if not execucao_id or not tipo_id or pk in (None, ""):
        return
    # ignore_conflicts: o mesmo registro salvo varias vezes na tarefa vira uma linha so.
    TarefaRegistro.objects.bulk_create([TarefaRegistro(
        execucao_id=execucao_id, content_type_id=tipo_id, object_pk=str(pk)[:64],
        descricao=str(descricao or "")[:200],
    )], ignore_conflicts=True)


def vincular_objeto(execucao_id, modelo, pk):
    """Envio: o registro enviado, mesmo que o envio nao altere nada no hub."""
    if modelo is None:
        return
    obj = modelo._base_manager.filter(pk=pk).first()
    tipo = ContentType.objects.get_for_model(modelo).pk
    vincular(execucao_id, tipo, pk, str(obj) if obj is not None else "")


def _ao_gravar_log(sender, instance, created, **kwargs):
    tarefa_id = (instance.additional_data or {}).get("tarefa_id") if created else None
    if tarefa_id:
        vincular(tarefa_id, instance.content_type_id, instance.object_pk, instance.object_repr)


def ligar():
    from auditlog.models import LogEntry

    post_save.connect(_ao_gravar_log, sender=LogEntry, dispatch_uid="starhub_tarefa_registro")
