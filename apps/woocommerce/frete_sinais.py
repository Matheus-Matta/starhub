"""Mudou uma tabela ou faixa de frete: as lojas Woo com frete ligado recebem as zonas de novo.

Depois do commit (rollback nao reenvia) e uma tarefa por loja: se ja ha uma na fila
(Pendente), a mudanca seguinte nao cria outra, porque a da fila le as tabelas quando
roda. A importacao de planilha (origem "importacao") nao reenvia por linha: manda
`tabelas_alteradas` uma vez no fim (apps/logistica/tasks.py).
"""

from django.db import transaction
from django.db.models.signals import post_delete, post_save

from apps.core import origem
from apps.core.tarefas import enfileirar
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.logistica.models import FaixaCep, TabelaFrete
from apps.logistica.sinais import tabelas_alteradas

TIPO = ExecucaoIntegracao.Tipo.FRETE_CHECKOUT


def enfileirar_frete(configuracao, remover=False):
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=TIPO, parametros={"remover": remover})
    from apps.woocommerce.tasks import frete_woocommerce

    resultado = enfileirar(frete_woocommerce, str(execucao.pk))
    ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(celery_task_id=resultado.id or "")
    return execucao


def _reenviar():
    from apps.woocommerce.frete_envio import frete_ligado

    lojas = ConfiguracaoIntegracao.objects.filter(
        plataforma=ConfiguracaoIntegracao.Plataforma.WOOCOMMERCE, active=True)
    for configuracao in lojas:
        na_fila = ExecucaoIntegracao.objects.filter(
            configuracao=configuracao, tipo=TIPO, status=ExecucaoIntegracao.Status.PENDENTE)
        if frete_ligado(configuracao) and not na_fila.exists():
            enfileirar_frete(configuracao)


def _agendar():
    # Apagar uma tabela apaga as faixas: um sinal por faixa, uma tarefa so por commit. A
    # fila do on_commit e a do Django: rollback a esvazia, nada fica marcado por engano.
    conexao = transaction.get_connection()
    if any(item[1] is _reenviar for item in conexao.run_on_commit):
        return
    transaction.on_commit(_reenviar)


def tabelas_mudaram(sender=None, **kwargs):
    if origem.atual() != "importacao":
        _agendar()


def lote_importado(sender=None, **kwargs):
    _agendar()


def conectar():
    for modelo in (TabelaFrete, FaixaCep):
        post_save.connect(tabelas_mudaram, sender=modelo, dispatch_uid=f"woo_frete_{modelo}")
        post_delete.connect(tabelas_mudaram, sender=modelo,
                            dispatch_uid=f"woo_frete_del_{modelo}")
    tabelas_alteradas.connect(lote_importado, dispatch_uid="woo_frete_lote")
