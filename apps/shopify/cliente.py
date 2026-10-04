"""Transporte HTTP da Admin GraphQL API do Shopify; nenhuma regra de negocio aqui."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.shopify.consultas import (
    CONSULTA_WEBHOOKS,
    CONSULTAS,
    CONTAGENS,
    MUTATION_EXCLUIR_WEBHOOK,
    MUTATION_WEBHOOK,
)


class ShopifyErro(RuntimeError):
    pass


class ShopifyClient:
    def __init__(self, configuracao, timeout=30):
        self.configuracao = configuracao
        self.timeout = timeout
        self.endpoint = (
            f"https://{configuracao.dominio_loja}/admin/api/"
            f"{configuracao.versao_api}/graphql.json"
        )

    def graphql(self, query, variables=None):
        corpo = json.dumps({"query": query, "variables": variables or {}}).encode()
        requisicao = Request(self.endpoint, data=corpo, method="POST", headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.configuracao.token_acesso,
        })
        try:
            with urlopen(requisicao, timeout=self.timeout) as resposta:
                dados = json.loads(resposta.read().decode())
        except HTTPError as erro:
            detalhe = erro.read().decode(errors="replace")[:500]
            raise ShopifyErro(f"Shopify respondeu HTTP {erro.code}: {detalhe}") from erro
        except (URLError, TimeoutError, json.JSONDecodeError) as erro:
            raise ShopifyErro(f"Nao foi possivel consultar o Shopify: {erro}") from erro
        if dados.get("errors"):
            mensagens = "; ".join(item.get("message", str(item)) for item in dados["errors"])
            raise ShopifyErro(mensagens)
        return dados.get("data", {})

    def listar(self, recurso):
        raiz, query = CONSULTAS[recurso]
        cursor = None
        while True:
            conexao = self.graphql(query, {"cursor": cursor})[raiz]
            yield from conexao.get("nodes", [])
            pagina = conexao.get("pageInfo", {})
            if not pagina.get("hasNextPage"):
                break
            cursor = pagina.get("endCursor")

    def contar(self, recurso):
        """Quantos itens a loja tem (para a barra de progresso); None se nao der para saber."""
        campo = CONTAGENS.get(CONSULTAS[recurso][0])
        if campo is None:
            return None
        # limit: null pede o numero exato (o padrao para em 10.000); campo sem o argumento
        # recusa, e ai vale a contagem padrao.
        for argumentos in ("(limit: null)", ""):
            try:
                contagem = (self.graphql(f"query {{ {campo}{argumentos} {{ count }} }}") or {})
            except ShopifyErro:
                continue
            numero = (contagem.get(campo) or {}).get("count")
            return int(numero) if numero is not None else None
        return None

    def cadastrar_webhook(self, topico, uri):
        dados = self.graphql(MUTATION_WEBHOOK, {
            "topic": topico,
            "webhook": {"uri": uri, "format": "JSON"},
        }).get("webhookSubscriptionCreate", {})
        erros = dados.get("userErrors") or []
        if erros:
            raise ShopifyErro("; ".join(item.get("message", str(item)) for item in erros))
        return dados.get("webhookSubscription", {})

    def listar_webhooks(self):
        cursor = None
        while True:
            conexao = self.graphql(CONSULTA_WEBHOOKS, {"cursor": cursor})[
                "webhookSubscriptions"
            ]
            yield from conexao.get("nodes", [])
            pagina = conexao.get("pageInfo", {})
            if not pagina.get("hasNextPage"):
                break
            cursor = pagina.get("endCursor")

    def excluir_webhook(self, webhook_id):
        dados = self.graphql(MUTATION_EXCLUIR_WEBHOOK, {"id": webhook_id}).get(
            "webhookSubscriptionDelete", {}
        )
        erros = dados.get("userErrors") or []
        if erros:
            raise ShopifyErro("; ".join(item.get("message", str(item)) for item in erros))
        return dados.get("deletedWebhookSubscriptionId")
