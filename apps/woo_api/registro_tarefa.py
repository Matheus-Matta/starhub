"""Cada escrita da API Woo (e cada erro, ate de leitura) vira uma tarefa na tela de Tarefas.

    POST /wc/v3/products       -> tarefa "Requisicao da API Woo": corpo, resposta, HTTP 201
    PUT  /wc/v3/products/9     -> 404/400/409: a tarefa fica "Falhou" com o codigo e a mensagem
    POST /wc/v3/products/batch -> item com erro vira "Concluida com falhas", um por item
    GET  /wc/v3/products       -> so registra se der erro (o ERP le o tempo todo)

A tarefa e aberta ANTES de processar: os logs gravados no caminho levam o id dela
(apps/core/origem.py) e o botao "Tarefas" do produto acha a requisicao que o mudou.
Requisicao sem credencial valida nao tem conta e fica so no log do servidor.
"""

import json
import logging

from django.http.request import RawPostDataException
from django.utils import timezone

from apps.integracoes import trafego
from apps.integracoes.falhas import MAX_FALHAS, item
from apps.integracoes.models import ExecucaoIntegracao

ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}
SEGREDOS = ("password", "senha", "token", "secret", "segredo")
Status = ExecucaoIntegracao.Status
logger = logging.getLogger(__name__)


def _mascarar(valor):
    if isinstance(valor, dict):
        return {chave: "***" if any(s in str(chave).lower() for s in SEGREDOS)
                else _mascarar(item_) for chave, item_ in valor.items()}
    if isinstance(valor, list):
        return [_mascarar(item_) for item_ in valor]
    return valor


def _corpo(django_request):
    """Corpo para guardar; multipart (imagem) nao e lido inteiro na memoria por isto."""
    if "multipart" in (django_request.content_type or ""):
        return f"<multipart de {django_request.META.get('CONTENT_LENGTH') or '?'} bytes>"
    try:
        corpo = trafego.corpo_guardavel(django_request.body)
    except RawPostDataException:
        return "<corpo ja lido; nao guardado>"
    return _mascarar(corpo)


def abrir(request, chave, sempre=False):
    """Tarefa aberta da requisicao; None para leitura (so vira tarefa se falhar)."""
    if request.method not in ESCRITA and not sempre:
        return None
    django_request = request._request
    return ExecucaoIntegracao.objects.create(
        tipo=ExecucaoIntegracao.Tipo.API_WOO, status=Status.PROCESSANDO, total=1,
        etapa=f"{request.method} {django_request.path}"[:150], iniciada_em=timezone.now(),
        parametros={"requisicao": trafego.requisicao(django_request, _corpo(django_request)),
                    "chave": str(chave)},
    )


def _dados(response):
    dados = getattr(response, "data", None)
    if dados is not None:
        return dados
    try:
        return json.loads(response.content or b"null")
    except (ValueError, AttributeError):
        return None


def _erro(status, dados):
    if isinstance(dados, dict) and dados.get("code"):
        return f"HTTP {status} {dados['code']}: {dados.get('message', '')}"
    return f"HTTP {status}: {str(dados)[:500] if dados else 'sem corpo'}"


def _falhas_do_lote(dados):
    if not isinstance(dados, dict):
        return []
    falhas = []
    for operacao in ("create", "update", "delete"):
        for resultado in dados.get(operacao) or []:
            erro = resultado.get("error") if isinstance(resultado, dict) else None
            if erro:
                motivo = f"{erro.get('code', '')}: {erro.get('message', '')}".strip(": ")
                falhas.append(item(operacao, motivo, resultado.get("id", "")))
    return falhas


def fechar(execucao, response):
    status = response.status_code
    dados = _dados(response)
    falhas = _falhas_do_lote(dados) if status < 400 else []
    if status >= 400:
        situacao, mensagem = Status.FALHOU, _erro(status, dados)
        falhas = [item("", mensagem)]
    elif falhas:
        situacao = Status.CONCLUIDA_COM_FALHAS
        mensagem = (f"HTTP {status}: {len(falhas)} item(ns) do lote recusado(s) "
                    f"(primeiro: {falhas[0]['motivo']}).")
    else:
        situacao, mensagem = Status.CONCLUIDA, f"HTTP {status}"
    corpo = json.dumps(dados, ensure_ascii=False, default=str) if dados is not None else ""
    parametros = {**(execucao.parametros or {}),
                  "resposta": trafego.resposta(status, corpo, dict(response.items()))}
    ExecucaoIntegracao.all_objects.filter(pk=execucao.pk).update(
        status=situacao, etapa=f"HTTP {status}", progresso=100, processados=1,
        mensagem=mensagem[:4000], falhas=falhas[:MAX_FALHAS], parametros=parametros,
        concluida_em=timezone.now(), updated_at=timezone.now())


def sem_resposta(execucao):
    """Erro que estourou fora do tratador do DRF (500): a tarefa nao fica 'Processando'."""
    mensagem = "HTTP 500: erro interno ao processar a requisicao; veja o log do servidor."
    ExecucaoIntegracao.all_objects.filter(pk=execucao.pk, status=Status.PROCESSANDO).update(
        status=Status.FALHOU, etapa="HTTP 500", progresso=100, mensagem=mensagem,
        falhas=[item("", mensagem)], concluida_em=timezone.now(), updated_at=timezone.now())


def registrar_erro(request, chave, response):
    """Leitura que falhou (ou recusa antes de abrir): tarefa ja encerrada."""
    try:
        fechar(abrir(request, chave, sempre=True), response)
    except Exception:  # o registro nunca derruba a resposta que o ERP espera
        logger.exception("Nao registrou a tarefa do erro %s em %s", response.status_code,
                         request.path)
