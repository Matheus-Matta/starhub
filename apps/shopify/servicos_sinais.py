"""Servico ou regra mudou: o produto do servico na Shopify e reenviado (servicos_envio.py).

A regra muda os precos do servico, e cada preco e uma variante la. Quais produtos do
catalogo levam o servico nao vai para a Shopify: o bloco do tema pergunta na hora
(servicos_publico.py). Uma tarefa por servico por transacao (envio/transacao.py).
"""

from django.db.models.signals import post_delete, post_save

from apps.integracoes.envio import transacao
from apps.integracoes.envio.distribuidor import _enfileirar, obter
from apps.integracoes.models import ConfiguracaoIntegracao

RECURSO = "servicos"


def servico_mudou(conta_id, servico_id, operacao):
    for configuracao in obter().candidatos(conta_id):
        if (configuracao.plataforma == ConfiguracaoIntegracao.Plataforma.SHOPIFY
                and configuracao.enviar_servicos):
            transacao.agendar(configuracao.pk, RECURSO, operacao, servico_id, _enfileirar)


def _salvo(sender, instance, created, raw=False, **kwargs):
    if not raw:
        servico_mudou(instance.account_id, instance.pk, "create" if created else "update")


def _excluido(sender, instance, **kwargs):
    servico_mudou(instance.account_id, instance.pk, "delete")


def _regra(sender, instance, raw=False, **kwargs):
    if not raw:
        servico_mudou(instance.account_id, instance.servico_id, "update")


def conectar():
    from apps.loja.models import RegraServico, Servico

    post_save.connect(_salvo, sender=Servico, dispatch_uid="shopify-servico")
    post_delete.connect(_excluido, sender=Servico, dispatch_uid="shopify-servico-del")
    post_save.connect(_regra, sender=RegraServico, dispatch_uid="shopify-regra")
    post_delete.connect(_regra, sender=RegraServico, dispatch_uid="shopify-regra-del")
