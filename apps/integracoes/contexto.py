"""Loja e avisos da tarefa de marketplace em andamento.

    contexto = ContextoMarketplace("suri")
    with contexto.usando_configuracao(cfg), contexto.coletando_avisos() as avisos:
        ...  # importar um pedido pode precisar buscar na loja o produto que falta
        contexto.avisar("Imagem nao importada", recurso="produtos", id=15)

Aviso e problema que nao derruba a execucao (imagem que nao baixou, SKU repetido):
vira linha na tabela de falhas da tarefa.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from apps.integracoes.falhas import item


class ContextoMarketplace:
    def __init__(self, nome):
        self._configuracao = ContextVar(f"{nome}_configuracao", default=None)
        self._avisos = ContextVar(f"{nome}_avisos", default=None)

    def configuracao_atual(self):
        return self._configuracao.get()

    @contextmanager
    def usando_configuracao(self, configuracao):
        token = self._configuracao.set(configuracao)
        try:
            yield configuracao
        finally:
            self._configuracao.reset(token)

    def avisar(self, texto, *, recurso="", id="", descricao="", id_externo=""):  # noqa: A002
        avisos = self._avisos.get()
        if avisos is not None:
            avisos.append(item(recurso, texto, id, descricao, str(id_externo)))

    @contextmanager
    def coletando_avisos(self):
        token = self._avisos.set([])
        try:
            yield self._avisos.get()
        finally:
            self._avisos.reset(token)

    @contextmanager
    def ambiente(self, configuracao):
        """O `ambiente` de apps.integracoes.execucao.executar."""
        with self.usando_configuracao(configuracao), self.coletando_avisos() as avisos:
            yield avisos
