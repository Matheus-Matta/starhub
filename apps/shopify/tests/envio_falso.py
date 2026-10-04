"""Apoio dos testes de envio: marketplace e cliente GraphQL falsos (sem rede)."""

from types import SimpleNamespace

from apps.shopify.cliente import ShopifyErro


class GraphQLFalso:
    def __init__(self, respostas=None):
        self.respostas = respostas or {}
        self.chamadas = []

    def graphql(self, query, variables=None):
        self.chamadas.append((query, variables))
        for campo, resposta in self.respostas.items():
            if campo in query:
                return {campo: resposta}
        raise ShopifyErro("resposta nao prevista no teste")


def enviador(classe, **respostas):
    falso = GraphQLFalso(respostas)
    objeto = classe(SimpleNamespace(configuracao=None))
    objeto._cliente = falso
    return objeto, falso
