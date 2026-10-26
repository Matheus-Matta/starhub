"""Servico ou regra mudou: reenvia ao Suri os produtos que ganham ou perdem a variante.

O envio do produto (envio/produtos.py) ja monta os servicos na hora; aqui so se
descobre QUAIS produtos reenviar quando a mudanca nao passou pelo produto:

- os que a regra pega agora (ganham a variante ou mudam de preco);
- os que levam o servico no Suri hoje, pelo vinculo "servicos" (perdem a variante
  quando saem da regra: o PUT vai sem ela e o Suri a apaga).

Uma conta so de servico por transacao (envio/transacao.py junta as repeticoes: o
admin salva a regra, depois as linhas de produto e de categoria).
"""

from django.db.models.signals import m2m_changed, post_delete, post_save

from apps.core.models import ExternalReference
from apps.integracoes.envio import transacao
from apps.integracoes.envio.distribuidor import obter
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.suri import servicos as servicos_suri
from apps.suri import vinculos

RECURSO_AGENDAMENTO = "servicos"
RECURSO_ENVIO = "produtos"


def _pode_reenviar(configuracao):
    return (configuracao.enviar_servicos
            and configuracao.habilitado("enviar", "produtos", "update"))


def servico_mudou(conta_id, servico_id):
    for configuracao in obter().candidatos(conta_id):
        if (configuracao.plataforma == ConfiguracaoIntegracao.Plataforma.SURI
                and _pode_reenviar(configuracao)):
            transacao.agendar(configuracao.pk, RECURSO_AGENDAMENTO, "update", servico_id,
                              _reenviar)


def produtos_afetados(conta_id, servico_id):
    from apps.loja.models import RegraServico
    from apps.loja.services.servicos_regras import produtos_da_regra

    pks = set()
    for regra in RegraServico.all_objects.filter(account_id=conta_id, servico_id=servico_id):
        pks |= set(produtos_da_regra(regra).values_list("pk", flat=True))
    no_suri = ExternalReference.all_objects.filter(
        account_id=conta_id, platform=vinculos.PLATAFORMA, entity_type="produtos")
    pks |= {int(pk) for pk in no_suri.filter(
        external_id__in=servicos_suri.produtos_no_suri(servico_id))
        .values_list("object_id", flat=True)}
    # So o que ja esta no Suri: produto novo vai inteiro pelo envio dele, com os servicos.
    vinculados = set(no_suri.filter(object_id__in=[str(pk) for pk in pks])
                     .values_list("object_id", flat=True))
    return sorted(pk for pk in pks if str(pk) in vinculados)


def _reenviar(configuracao_id, _recurso, _operacao, servico_id):
    from apps.integracoes.envio.distribuidor import _enfileirar

    configuracao = ConfiguracaoIntegracao.all_objects.filter(pk=configuracao_id).first()
    if configuracao is None or not _pode_reenviar(configuracao):
        return
    for pk in produtos_afetados(configuracao.account_id, servico_id):
        _enfileirar(configuracao_id, RECURSO_ENVIO, "update", pk)


def _do_servico(sender, instance, raw=False, **kwargs):
    if not raw:
        servico_mudou(instance.account_id, instance.pk)


def _da_regra(sender, instance, raw=False, **kwargs):
    if not raw:
        servico_mudou(instance.account_id, instance.servico_id)


def _da_linha(sender, instance, raw=False, **kwargs):
    # Linha do inline (tabela M2M automatica): a regra diz a conta e o servico.
    from apps.loja.models import RegraServico

    regra = RegraServico.all_objects.filter(pk=instance.regraservico_id).values(
        "account_id", "servico_id").first()
    if regra and not raw:
        servico_mudou(regra["account_id"], regra["servico_id"])


def _m2m(sender, instance, action, reverse, **kwargs):
    # reverse: produto.regras_servico.add(...) mexe em varias regras; fica sem envio.
    if action in {"post_add", "post_remove", "post_clear"} and not reverse:
        servico_mudou(instance.account_id, instance.servico_id)


def conectar():
    from apps.loja.models import RegraServico, Servico

    for modelo, receptor in ((Servico, _do_servico), (RegraServico, _da_regra)):
        rotulo = modelo._meta.label
        post_save.connect(receptor, sender=modelo, dispatch_uid=f"suri-servico-{rotulo}")
        post_delete.connect(receptor, sender=modelo, dispatch_uid=f"suri-servico-del-{rotulo}")
    for campo in ("produtos", "categorias"):
        through = getattr(RegraServico, campo).through
        post_save.connect(_da_linha, sender=through, dispatch_uid=f"suri-regra-{campo}")
        post_delete.connect(_da_linha, sender=through, dispatch_uid=f"suri-regra-del-{campo}")
        m2m_changed.connect(_m2m, sender=through, dispatch_uid=f"suri-regra-m2m-{campo}")
