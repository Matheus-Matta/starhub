"""Configuracao da loja Shopify da execucao em andamento.

O importador de pedido recebe so o JSON do pedido; quando precisa consultar o
Shopify (produto que o hub nao conhece), pega a loja daqui. Quem liga e
`tasks._executar`, em volta de toda tarefa da integracao.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from apps.integracoes.falhas import item

_configuracao = ContextVar("shopify_configuracao", default=None)


def configuracao_atual():
    return _configuracao.get()


@contextmanager
def usando_configuracao(configuracao):
    token = _configuracao.set(configuracao)
    try:
        yield configuracao
    finally:
        _configuracao.reset(token)


# Problema que nao derruba a execucao (ex.: imagem que nao baixou) mas que o
# operador precisa ver na tarefa, em vez de so no log do worker. Cada aviso vira uma
# linha da tabela de falhas (apps/integracoes/falhas.py) e a tarefa termina
# "Concluida com falhas". Identifique o item sempre que der: recurso, id do hub,
# descricao (nome/SKU/numero) e id externo do Shopify.
_avisos = ContextVar("shopify_avisos", default=None)


def avisar(texto, *, recurso="", id="", descricao="", id_externo=""):  # noqa: A002
    avisos = _avisos.get()
    if avisos is not None:
        avisos.append(item(recurso, texto, id, descricao, id_externo))


@contextmanager
def coletando_avisos():
    token = _avisos.set([])
    try:
        yield _avisos.get()
    finally:
        _avisos.reset(token)
