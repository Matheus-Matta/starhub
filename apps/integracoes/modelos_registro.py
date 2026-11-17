"""Quais registros do hub cada tarefa tocou: o botao "Tarefas" da edicao filtra por aqui.

Antes o alvo da tarefa so existia dentro do JSON de parametros (e cada tipo guardava
de um jeito): nao dava para perguntar "que tarefas mexeram nesta variante?". A linha
nasce sozinha a cada log gravado dentro da tarefa (apps/integracoes/registros_tarefa.py)
e, no envio, tambem para o registro enviado (o envio pode nao alterar nada no hub).

Sem conta propria: a conta e a da tarefa, e a lista de tarefas ja filtra por ela.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import models


class TarefaRegistro(models.Model):
    execucao = models.ForeignKey(
        "integracoes.ExecucaoIntegracao", verbose_name="tarefa", on_delete=models.CASCADE,
        related_name="registros",
    )
    content_type = models.ForeignKey(
        ContentType, verbose_name="tipo de registro", on_delete=models.CASCADE)
    object_pk = models.CharField("id do registro", max_length=64)
    descricao = models.CharField("registro", max_length=200, blank=True)
    criado_em = models.DateTimeField("quando", auto_now_add=True)

    class Meta:
        verbose_name = "registro da tarefa"
        verbose_name_plural = "registros da tarefa"
        ordering = ["content_type_id", "object_pk"]
        constraints = [models.UniqueConstraint(
            # Varios logs do mesmo registro na mesma tarefa (produto salvo duas vezes)
            # viram uma linha so; ignore_conflicts no insert depende deste indice.
            fields=["execucao", "content_type", "object_pk"], name="tarefa_registro_unico",
        )]
        indexes = [models.Index(fields=["content_type", "object_pk"],
                                name="tarefa_registro_alvo")]

    def __str__(self):
        return self.descricao or f"{self.content_type} #{self.object_pk}"
