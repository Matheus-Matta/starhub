"""Tarefa que leva uma alteracao do hub para um marketplace (agendada pelo Distribuidor)."""

import logging

from celery import shared_task
from django.utils import timezone

from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes import conferencia  # noqa: F401 - registra a tarefa do beat no worker
from apps.integracoes import exportar as exportador
from apps.integracoes.envio import registro
from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.progresso import registrar
from apps.integracoes.registros_tarefa import vincular_objeto
from apps.integracoes.tarefa_estado import _abrir, _concluir, _falhar, _gravar  # noqa: F401
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
        # Com a tarefa no contexto, o que o envio gravar no hub aponta para ela.
        with origem(configuracao.plataforma, via=configuracao.nome, tarefa=execucao.pk):
            return _enviar(self, configuracao, execucao, (recurso, operacao, pk), etapa)


def _enviar(task, configuracao, execucao, alvo, etapa):
    recurso, operacao, pk = alvo
    classe = registro.obter(configuracao.plataforma)
    try:
        if classe is None:
            raise EnvioNaoSuportado(f"nenhum enviador registrado para {configuracao.plataforma}")
        marketplace = classe(configuracao)
        enviador = marketplace.enviador(recurso)
        # O envio pode nao alterar nada no hub: sem isto a tarefa nao apareceria no
        # botao "Tarefas" do produto enviado.
        vincular_objeto(execucao.pk, getattr(enviador, "modelo", None), pk)
        mensagem = marketplace.enviar(recurso, operacao, pk)
    except EnvioNaoSuportado as erro:
        mensagem = f"ignorado: {erro}"
    except Exception as erro:  # rede/API: repete com espera; esgotou, fica no rastro
        if deve_repetir(task.request):
            _gravar(execucao, etapa=f"Nova tentativa ({task.request.retries + 1})")
            raise task.retry(
                exc=erro, countdown=30 * 2 ** task.request.retries,
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
        configuracao.plataforma, via=configuracao.nome, tarefa=execucao.pk
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
            # "produtos": so os escolhidos no botao/acao do produto (exportar.py).
            produtos = (execucao.parametros or {}).get("produtos")
            extra = {"produtos": produtos} if produtos else {}
            resumo = exportador.exportar_dados(configuracao, recursos, progresso, **extra)
        except Exception as erro:  # a tarefa precisa persistir o erro antes de terminar
            _gravar(execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
                    mensagem=str(erro)[:4000], concluida_em=timezone.now())
            return {"status": "failed", "message": str(erro)}
        status, mensagem = resumo.status(), resumo.texto()
        # Item com erro nao para os outros (exportar._enviar); o status diz se houve algum.
        _gravar(execucao, status=status, etapa=status.label, progresso=100, mensagem=mensagem,
                falhas=resumo.detalhes, concluida_em=timezone.now())
        return {"status": str(status), "message": mensagem}


@shared_task(bind=True, ignore_result=True)
def despachar_envios_pendentes(self, token=None, eventos=None):
    """Processa a rajada inteira usando uma mensagem do broker."""
    from apps.integracoes.envio import lote

    if eventos is None:
        token, eventos = lote.iniciar()
    else:
        eventos = [lote.Evento(**evento) for evento in eventos]
    if not token:
        return {"processados": 0, "pendentes": 0}
    processados, falharam, finalizar = 0, [], True
    try:
        for evento in eventos:
            try:
                # Chamada local: o lote inteiro ocupa uma mensagem do broker. A tarefa
                # individual continua existindo para Retomar e para compatibilidade.
                resultado = enviar_alteracao.run(
                    evento.configuracao_id, evento.recurso, evento.operacao, evento.pk
                )
            except Exception:
                logger.exception(
                    "Envio em lote falhou antes de registrar o resultado: %s %s",
                    evento.recurso, evento.pk,
                )
                falharam.append(evento)
                continue
            if resultado.get("status") == "failed":
                falharam.append(evento)
                continue
            lote.confirmar(token, evento)
            processados += 1
        if falharam and deve_repetir(self.request):
            # Uma mensagem repete todas as falhas do lote; os sucessos ja foram
            # confirmados e nao voltam. A trava impede o beat de pegar as mesmas falhas.
            finalizar = False
            raise self.retry(
                args=(token, [vars(evento) for evento in falharam]),
                countdown=30 * 2 ** self.request.retries,
            )
        for evento in falharam:
            lote.confirmar(token, evento)
            processados += 1
    finally:
        if finalizar:
            lote.finalizar(token)
    return {"processados": processados, "pendentes": len(eventos) - processados}
