"""Porta de entrada da sincronizacao em etapas (tela "Sincronizar loja").

A tela pergunta a direcao e os recursos; aqui se valida contra a configuracao, se
cria a tarefa (ExecucaoIntegracao) e se agenda o Celery so depois do commit.

Uma sincronizacao por vez por configuracao: quem garante e o indice condicional
`integracao_uma_sincronizacao_por_vez` do banco. A consulta antes do create so
serve para dar a mensagem sem gastar um IntegrityError; dois cliques ao mesmo
tempo passam os dois por ela, e o banco segura o segundo.
"""

import logging
from datetime import timedelta
from importlib import import_module

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.tarefas import enfileirar
from apps.integracoes.envio import registro
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.permissoes import RECURSOS

IMPORTAR, EXPORTAR = "importar", "exportar"
DIRECOES = (IMPORTAR, EXPORTAR)

# Quem busca os dados de cada plataforma (import tardio: o app do marketplace
# depende de integracoes, nao o contrario).
IMPORTADORES = {"shopify": "apps.shopify.tasks.sincronizar_shopify",
                "woocommerce": "apps.woocommerce.tasks.sincronizar_woocommerce",
                "suri": "apps.suri.tasks.sincronizar_suri"}
EXPORTADOR = "apps.integracoes.tasks.exportar_dados"

EM_ANDAMENTO = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)
TIPOS = {IMPORTAR: ExecucaoIntegracao.Tipo.SINCRONIZAR, EXPORTAR: ExecucaoIntegracao.Tipo.EXPORTAR}

# Sinal de vida = updated_at, renovado a cada progresso. 30 min cobre a pagina mais
# lenta da API do marketplace com folga; menos que isso liberaria uma que esta viva.
TEMPO_SEM_SINAL = timedelta(minutes=30)

logger = logging.getLogger(__name__)


class SincronizacaoEmAndamento(Exception):
    def __init__(self, execucao):
        self.execucao = execucao  # a que ja esta na fila ou rodando
        super().__init__(
            "Ja existe uma sincronizacao desta loja na fila ou rodando; "
            "acompanhe a tarefa e espere ela terminar para criar outra."
        )


def _motivo(configuracao, direcao, recurso, rotulo):
    if direcao == IMPORTAR:
        if configuracao.habilitado("receber", recurso, "get"):
            return ""
        return f"Ligue Receber > {rotulo} > Buscar"
    classe = registro.obter(configuracao.plataforma)
    if classe is None or classe(configuracao).enviador(recurso) is None:
        return f"O envio de {rotulo.lower()} para esta plataforma ainda nao existe"
    if configuracao.habilitado("enviar", recurso, "create") or configuracao.habilitado(
        "enviar", recurso, "update"
    ):
        return ""
    return f"Ligue Enviar > {rotulo} > Criar ou Atualizar"


def recursos_disponiveis(configuracao, direcao):
    _validar_direcao(direcao)
    saida = []
    for recurso, rotulo in RECURSOS:
        motivo = _motivo(configuracao, direcao, recurso, rotulo)
        saida.append({
            "recurso": recurso, "rotulo": rotulo, "permitido": not motivo, "motivo": motivo,
        })
    return saida


def _validar_direcao(direcao):
    if direcao not in DIRECOES:
        raise ValueError("Escolha a direcao: Importar (loja -> StarHub) ou Exportar.")


def _validar_recursos(configuracao, direcao, recursos):
    if isinstance(recursos, str):
        recursos = [recursos]
    pedidos = {str(r) for r in recursos or ()}
    if not pedidos:
        raise ValueError("Escolha ao menos um dado para sincronizar.")
    disponiveis = {item["recurso"]: item for item in recursos_disponiveis(configuracao, direcao)}
    desconhecidos = sorted(pedidos - set(disponiveis))
    if desconhecidos:
        raise ValueError(f"Dado desconhecido: {', '.join(desconhecidos)}. Recarregue a tela.")
    bloqueados = [
        f"{item['rotulo']} ({item['motivo']})"
        for recurso, item in disponiveis.items()
        if recurso in pedidos and not item["permitido"]
    ]
    if bloqueados:
        raise ValueError(
            "A configuracao nao permite: " + "; ".join(bloqueados)
            + ". Ajuste o fluxo de dados e salve antes de sincronizar."
        )
    # Ordem da matriz, nao a do formulario: o rastro fica igual para o mesmo pedido.
    return [recurso for recurso, _ in RECURSOS if recurso in pedidos]


def _tarefa(configuracao, direcao):
    caminho = EXPORTADOR if direcao == EXPORTAR else IMPORTADORES.get(configuracao.plataforma)
    if caminho is None:
        raise ValueError("Importar desta plataforma ainda nao existe no StarHub.")
    modulo, nome = caminho.rsplit(".", 1)
    return getattr(import_module(modulo), nome)


def em_andamento(configuracao):
    return ExecucaoIntegracao.all_objects.filter(
        configuracao_id=configuracao.pk, status__in=EM_ANDAMENTO, tipo__in=TIPOS.values()
    ).order_by("created_at").first()


def liberar_travada(execucao, sem_sinal_antes_de=None):
    """Marca como FALHOU a execucao aberta cujo worker sumiu; devolve se marcou.

    O filtro vai no UPDATE (e nao num `if` antes): se o worker der sinal entre a
    leitura e a gravacao, a linha nao casa e a execucao viva nao e derrubada.
    """
    ultimo_sinal = timezone.localtime(execucao.updated_at).strftime("%d/%m/%Y %H:%M")
    consulta = ExecucaoIntegracao.all_objects.filter(pk=execucao.pk, status__in=EM_ANDAMENTO)
    if sem_sinal_antes_de is not None:
        consulta = consulta.filter(updated_at__lt=sem_sinal_antes_de)
    return bool(consulta.update(
        status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
        concluida_em=timezone.now(), updated_at=timezone.now(),
        mensagem=f"Interrompida: sem sinal do worker desde {ultimo_sinal}; "
        "a sincronizacao nova foi liberada.",
    ))


def iniciar(configuracao, direcao, recursos):
    _validar_direcao(direcao)
    recursos = _validar_recursos(configuracao, direcao, recursos)
    tarefa = _tarefa(configuracao, direcao)
    existente = em_andamento(configuracao)
    if existente is not None and liberar_travada(
        existente, sem_sinal_antes_de=timezone.now() - TEMPO_SEM_SINAL
    ):
        existente = em_andamento(configuracao)
    if existente is not None:
        raise SincronizacaoEmAndamento(existente)
    try:
        # Savepoint: o IntegrityError do indice nao pode quebrar a transacao da requisicao.
        with transaction.atomic():
            execucao = ExecucaoIntegracao.objects.create(
                account_id=configuracao.account_id,
                configuracao=configuracao,
                tipo=TIPOS[direcao],
                parametros={"direcao": direcao, "recursos": recursos},
            )
    except IntegrityError:
        existente = em_andamento(configuracao)
        if existente is None:  # a outra terminou entre o create e a releitura
            raise
        raise SincronizacaoEmAndamento(existente) from None
    transaction.on_commit(lambda: _enfileirar(tarefa, execucao.pk))
    return execucao


def _enfileirar(tarefa, execucao_id):
    try:
        resultado = enfileirar(tarefa, str(execucao_id))
    except Exception as erro:  # broker fora: sem isto a pendente travaria a loja no indice
        logger.exception("Falha ao enfileirar a sincronizacao %s", execucao_id)
        ExecucaoIntegracao.all_objects.filter(pk=execucao_id, status__in=EM_ANDAMENTO).update(
            status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou", concluida_em=timezone.now(),
            mensagem=f"Nao foi possivel colocar na fila ({erro}). Confira o Redis/Celery "
            "e crie a tarefa de novo.",
        )
        return
    ExecucaoIntegracao.all_objects.filter(pk=execucao_id).update(celery_task_id=resultado.id or "")
