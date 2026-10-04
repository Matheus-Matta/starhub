"""Base dos enviadores do Shopify: cliente GraphQL, mutacao com userErrors e gid."""

from apps.core.models import ExternalReference
from apps.integracoes.envio.base import EnviadorRecurso
from apps.shopify.cliente import ShopifyClient, ShopifyErro

CONSULTA_LOCAL = "query { location { id } }"
VARIANTES = "variantes"  # entity_type das variantes, o mesmo do import (apps/shopify/produtos.py)


class RecursoShopify(EnviadorRecurso):
    """Enviador que fala com a Admin GraphQL API da loja do marketplace."""

    _cliente = None
    _local = None

    @property
    def cliente(self):
        # Um cliente por enviador: o envio de um recurso faz varias chamadas (ex.:
        # produto + variantes) e nao ha motivo para remontar endpoint e token a cada uma.
        if self._cliente is None:
            self._cliente = ShopifyClient(self.marketplace.configuracao)
        return self._cliente

    def mutacao(self, query, variaveis, campo):
        """Roda a mutation e devolve `data[campo]`; userErrors viram ShopifyErro.

        O Shopify responde HTTP 200 mesmo quando recusa a mutation: o motivo vem em
        `userErrors`. Sem esta checagem o envio seria dado como feito sem ter mudado nada.
        """
        dados = (self.cliente.graphql(query, variaveis) or {}).get(campo) or {}
        erros = dados.get("userErrors") or []
        if erros:
            raise ShopifyErro("; ".join(_mensagem(erro) for erro in erros))
        return dados

    @staticmethod
    def gid(tipo, id):
        """`gid("Product", 12)` -> "gid://shopify/Product/12"; gid pronto passa direto."""
        texto = str(id)
        return texto if texto.startswith("gid://") else f"gid://shopify/{tipo}/{texto}"


    def local_principal(self):
        """Gid do local principal da loja (`location` sem id devolve o principal)."""
        if self._local is None:
            dados = self.cliente.graphql(CONSULTA_LOCAL) or {}
            self._local = ((dados.get("location") or {}).get("id")) or ""
            if not self._local:
                raise ShopifyErro(
                    "A loja nao devolveu o local principal; confira o escopo read_locations "
                    "do app no Shopify."
                )
        return self._local

    def referencias_variantes(self):
        return ExternalReference.all_objects.filter(
            account_id=self.configuracao.account_id,
            platform=self.plataforma,
            entity_type=VARIANTES,
        )


def _mensagem(erro):
    campo = erro.get("field")
    caminho = ".".join(str(parte) for parte in campo) if campo else ""
    texto = erro.get("message") or str(erro)
    return f"{caminho}: {texto}" if caminho else texto
