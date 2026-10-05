"""Cadastra na loja WooCommerce os webhooks dos recursos ligados em Receber.

    https://hub/integracoes/woocommerce/webhook/<uuid da configuracao>/produtos/

Um endereco por recurso: o recurso vem da URL e a operacao do topico (product.updated).
O segredo que assina cada entrega e o segredo da chave da API (cs_), que o hub ja
guarda: sem um segredo a mais para o operador copiar. Recadastrar remove antes os
webhooks que apontam para o hub, senao a loja mandaria cada evento duas vezes.
"""

from apps.woocommerce.cliente import WooClient

# recurso do hub -> recurso no topico do Woo. Categoria e estoque nao tem webhook no
# Woo: categoria vem com o produto, estoque vem no product.updated.
TOPICOS = {"produtos": "product", "clientes": "customer", "pedidos": "order",
           "cupons": "coupon"}
OPERACOES = {"create": "created", "update": "updated", "delete": "deleted"}


def topicos_habilitados(configuracao):
    for recurso, nome in TOPICOS.items():
        for operacao, sufixo in OPERACOES.items():
            if configuracao.habilitado("receber", recurso, operacao):
                yield recurso, f"{nome}.{sufixo}"


def endereco(configuracao, recurso):
    return f"{configuracao.url_webhook.rstrip('/')}/{configuracao.uuid}/{recurso}/"


def cadastrar_webhooks(configuracao, progresso):
    if not configuracao.url_webhook:
        raise ValueError("Informe a URL publica dos webhooks antes de cadastrar.")
    cliente = WooClient(configuracao)
    itens = [(topico, endereco(configuracao, recurso))
             for recurso, topico in topicos_habilitados(configuracao)]
    nossos = {endereco(configuracao, recurso).rstrip("/") for recurso in TOPICOS}
    existentes = [webhook for webhook in cliente.listar("webhooks")
                  if (webhook.get("delivery_url") or "").rstrip("/") in nossos]
    total, posicao = len(existentes) + len(itens), 0
    for webhook in existentes:
        cliente.delete(f"webhooks/{webhook['id']}")
        posicao += 1
        progresso(posicao, total, f"Removendo webhook {webhook.get('topic', '')}")
    for topico, url in itens:
        cliente.post("webhooks", {"name": f"StarHub {topico}", "topic": topico,
                                  "delivery_url": url, "secret": configuracao.segredo_app,
                                  "status": "active"})
        posicao += 1
        progresso(posicao, total, f"Webhook {topico}")
    if existentes:
        return f"{len(existentes)} webhooks removidos; {len(itens)} cadastrados."
    return f"{len(itens)} webhooks cadastrados."
