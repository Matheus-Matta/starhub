"""Tarefa que leva uma alteracao do hub para um marketplace (agendada pelo Distribuidor)."""

import logging

from celery import shared_task
from django.utils import timezone

from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes import exportar as exportador
from apps.integracoes.envio import registro
from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.progresso import registrar
from apps.integracoes.tempo_real import publicar

TENTATIVAS = 3
ABERTAS = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)

logger = logging.getLogger(__name__)


def deve_repetir(request):
    # Eager (dev) roda dentro da requisicao do admin: repetir ali travaria a tela
    # e o erro subiria depois do commit. Chamada direta (teste, shell) tambem nao.
    if request.called_directly or request.is_eager:
        return False
    return request.retries < TENTATIVAS


def _gravar(execucao, **campos):
    # QuerySet.update() nao aplica auto_now: updated_at e o sinal de vida que a
    # sincronizacao usa para liberar uma execucao cujo worker morreu. So grava na
    # aberta: a liberada nao volta a andar nem troca o FALHOU por CONCLUIDA.
    gravou = ExecucaoIntegracao.all_objects.filter(pk=execucao.pk, status__in=ABERTAS).update(
        updated_at=timezone.now(), **campos
    )
    if gravou:
        publicar(execucao.pk)
    if not gravou and "status" in campos:
        logger.warning(
            "Execucao %s ja estava encerrada (liberada por falta de sinal?); "
            "resultado nao gravado: %s", execucao.pk, campos.get("mensagem", ""),
        )
    return gravou


def _abrir(configuracao, execucao_id, etapa, reenvio):
    if execucao_id:
        execucao = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).first()
        if execucao:
            return execucao
    return ExecucaoIntegracao.objects.create(
        configuracao=configuracao,
        tipo=ExecucaoIntegracao.Tipo.ENVIAR,
        status=ExecucaoIntegracao.Status.PROCESSANDO,
        etapa=etapa[:150],
        total=1,
        iniciada_em=timezone.now(),
        # O que o botao Retomar precisa para mandar de novo (apps/integracoes/retomar.py).
        parametros={"reenvio": reenvio},
    )


def _concluir(execucao, etapa, mensagem):
    _gravar(
        execucao, status=ExecucaoIntegracao.Status.CONCLUIDA, processados=1, progresso=100,
        etapa="Concluida", mensagem=f"{etapa}: {mensagem}"[:4000], concluida_em=timezone.now(),
    )


def _falhar(execucao, etapa, erro):
    _gravar(
        execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
        mensagem=f"{etapa}: {erro}"[:4000], concluida_em=timezone.now(),
    )


@shared_task(bind=True)
def enviar_alteracao(self, configuracao_id, recurso, operacao, pk, execucao_id=None):
    configuracao = ConfiguracaoIntegracao.all_objects.filter(pk=configuracao_id).first()
    if configuracao is None:
        return {"status": "ignored", "message": "configuracao removida"}
    etapa = f"{recurso} {operacao} {pk}"
    # Origem = destino: o que o envio gravar no hub (vinculo, id externo) vai para os
    # outros marketplaces, nunca de volta para este.
    with tenant_context(configuracao.account_id), origem(
        configuracao.plataforma, via=configuracao.nome
    ):
        execucao = _abrir(configuracao, execucao_id, etapa,
                          {"recurso": recurso, "operacao": operacao, "pk": str(pk)})
        classe = registro.obter(configuracao.plataforma)
        try:
            if classe is None:
                raise EnvioNaoSuportado(
                    f"nenhum enviador registrado para {configuracao.plataforma}"
                )
            mensagem = classe(configuracao).enviar(recurso, operacao, pk)
        except EnvioNaoSuportado as erro:
            mensagem = f"ignorado: {erro}"
        except Exception as erro:  # rede/API: repete com espera; esgotou, fica no rastro
            if deve_repetir(self.request):
                _gravar(execucao, etapa=f"Nova tentativa ({self.request.retries + 1})")
                raise self.retry(
                    exc=erro, countdown=30 * 2 ** self.request.retries,
                    kwargs={"execucao_id": str(execucao.pk)},
                ) from erro
            _falhar(execucao, etapa, erro)
            return {"status": "failed", "message": str(erro)}
        _concluir(execucao, etapa, mensagem)
        return {"status": "completed", "message": mensagem}


@shared_task
def exportar_dados(execucao_id):
    """Exportar em lote (tela "Sincronizar loja"): um rastro so, com progresso por registro."""
    execucao = ExecucaoIntegracao.all_objects.select_related("configuracao").get(pk=execucao_id)
    configuracao = execucao.configuracao
    recursos = (execucao.parametros or {}).get("recursos") or []
    with tenant_context(configuracao.account_id), origem(
        configuracao.plataforma, via=configuracao.nome
    ):
        # So comeca a que ainda esta aberta: a liberada por falta de sinal ja tem outra
        # no lugar, e reabri-la bateria no indice (uma por vez por loja). "running"
        # entra: e a mesma tarefa reentregue pelo broker depois de um worker cair.
        comecou = ExecucaoIntegracao.all_objects.filter(
            pk=execucao.pk, status__in=ABERTAS
        ).update(status=ExecucaoIntegracao.Status.PROCESSANDO, etapa="Iniciando",
                 iniciada_em=timezone.now(), updated_at=timezone.now())
        if not comecou:
            return {"status": "ignored", "message": "execucao ja encerrada"}
        publicar(execucao.pk)

        def progresso(processados, total, etapa):
            percentual = round(processados * 100 / total) if total else 0
            _gravar(execucao, processados=processados, total=total, progresso=percentual,
                    etapa=etapa[:150])
            registrar(processados, total, etapa[:150])

        try:
            resumo = exportador.exportar_dados(configuracao, recursos, progresso)
        except Exception as erro:  # a tarefa precisa persistir o erro antes de terminar
            _gravar(execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
                    mensagem=str(erro)[:4000], concluida_em=timezone.now())
            return {"status": "failed", "message": str(erro)}
        status, mensagem = resumo.status(), resumo.texto()
        # Item com erro nao para os outros (exportar._enviar); o status diz se houve algum.
        _gravar(execucao, status=status, etapa=status.label, progresso=100, mensagem=mensagem,
                falhas=resumo.detalhes, concluida_em=timezone.now())
        return {"status": str(status), "message": mensagem}
