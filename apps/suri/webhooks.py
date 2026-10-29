"""Webhook de pedidos do Suri Shop: cadastro (POST shop/hook) e processamento.

O Suri nao assina o webhook e a doc nao traz o formato do corpo. Por isso o corpo
so serve para achar o id do pedido; o pedido e lido de novo pela API, com o token
(`GET shop/orders/<id>`). Um POST forjado no endereco so faria o hub reler um pedido
verdadeiro.
"""

import logging

from apps.core.tenant.context import tenant_context
from apps.integracoes import sincronizacao
from apps.loja.models import Pedido
from apps.suri import vinculos
from apps.suri.cliente import SuriClient
from apps.suri.frete import frete_ligado, precisa_orcamento, responder_orcamento
from apps.suri.importar_pedidos import PedidoIgnorado, importar_pedido

logger = logging.getLogger(__name__)

# Eventos do chatbot (doc "Webhooks" da Suri): chegam no mesmo endereco e nao tem pedido.
EVENTOS_DO_CHATBOT = frozenset({
    "new-contact", "message-received", "change-queue", "finish-attendance", "message-sent",
    "message-send-error", "message-delivered", "message-read"})


def id_do_pedido(corpo):
    """Id do pedido no corpo: {"id"}, {"orderId"}, {"order": {...}} ou {"payload": {...}}."""
    if not isinstance(corpo, dict):
        return ""
    if "type" in corpo and "payload" in corpo:
        # Envelope {id, type, timestamp, payload}: o "id" de cima e do evento
        # ({chatbotId}:{guid}), nunca de um pedido.
        if corpo["type"] in EVENTOS_DO_CHATBOT:
            return ""
        return id_do_pedido(corpo["payload"])
    for chave in ("orderId", "OrderId", "id", "Id"):
        if corpo.get(chave) and isinstance(corpo[chave], str | int):
            return str(corpo[chave])
    for chave in ("order", "Order", "payload", "data"):
        achado = id_do_pedido(corpo.get(chave))
        if achado:
            return achado
    return ""


def menciona_pedido(corpo):
    """Mensagem do chat que traz compra (catalogo do WhatsApp: orderDetails ou payment)."""
    payload = corpo.get("payload") if isinstance(corpo, dict) else None
    if not isinstance(payload, dict):
        return False
    mensagem = payload.get("message") or payload.get("Message")
    return isinstance(mensagem, dict) and bool(
        mensagem.get("orderDetails") or mensagem.get("payment"))


def buscar_pedidos_recentes(configuracao):
    """Agenda o Sincronizar > Pedidos da loja; devolve se ha uma busca na fila.

    Varios eventos seguidos viram uma busca: o indice de uma sincronizacao por vez
    (sincronizacao.iniciar) segura as outras, e a da fila ja traz todos os pedidos.
    """
    try:
        with tenant_context(configuracao.account_id):
            sincronizacao.iniciar(configuracao, sincronizacao.IMPORTAR, ["pedidos"])
    except sincronizacao.SincronizacaoEmAndamento:
        logger.info("Webhook do Suri: busca de pedidos ja na fila (loja=%s).", configuracao.pk)
        return True
    except ValueError as erro:
        logger.warning("Webhook do Suri pode ser pedido, mas a busca nao foi feita na loja "
                       "%s: %s (ligue Receber > Pedidos > Buscar).", configuracao.pk, erro)
        return False
    logger.info("Webhook do Suri: buscando os pedidos recentes pela API (loja=%s).",
                configuracao.pk)
    return True


def endereco(configuracao):
    return f"{configuracao.url_webhook.rstrip('/')}/{configuracao.uuid}/"


def cadastrar_webhooks(configuracao, progresso):
    if not configuracao.url_webhook:
        raise ValueError("Informe a URL publica dos webhooks antes de cadastrar.")
    if not (configuracao.habilitado("receber", "pedidos", "create")
            or configuracao.habilitado("receber", "pedidos", "update")):
        raise ValueError("Ligue Receber > Pedidos > Criar ou Atualizar: o webhook do Suri "
                         "so manda pedidos.")
    progresso(0, 1, "Definindo o webhook da loja")
    # O Suri guarda um endereco so por loja: definir de novo troca o anterior.
    SuriClient(configuracao).post("shop/hook", {"url": endereco(configuracao)})
    progresso(1, 1, "Webhook definido")
    return f"Webhook de pedidos definido: {endereco(configuracao)}"


def processar_webhook(configuracao, pedido_id, progresso):
    progresso(0, 1, f"Pedido {pedido_id}")
    conhecido = vinculos.existente("pedidos", Pedido, pedido_id) is not None
    operacao = "update" if conhecido else "create"
    if not configuracao.habilitado("receber", "pedidos", operacao):
        return f"Receber > Pedidos > {'Atualizar' if conhecido else 'Criar'} esta desligado."
    dados = SuriClient(configuracao).get(f"shop/orders/{pedido_id}")
    if precisa_orcamento(dados) and frete_ligado(configuracao):
        mensagem = responder_orcamento(configuracao, dados)
        progresso(1, 1, "Orcamento respondido")
        return mensagem
    try:
        pedido, criado = importar_pedido(dados)
    except PedidoIgnorado as aviso:
        return str(aviso)
    progresso(1, 1, "Webhook processado")
    return f"Pedido {pedido.number} {'criado' if criado else 'atualizado'}."
