"""Marketplace falso (sem rede) para testar a arquitetura de envio.

Registrado so pela fixture `falsos` (conftest.py); grava cada chamada em `chamadas`.
"""

from apps.integracoes.envio.base import EnviadorRecurso, Marketplace
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Categoria, Produto, VarianteProduto

chamadas = []


class ProdutoFalso(EnviadorRecurso):
    recurso = "produtos"
    modelo = Produto

    def criar(self, obj):
        chamadas.append((self.plataforma, "criar", obj.pk))
        return f"{self.plataforma}-{obj.pk}"

    def atualizar(self, obj, external_id):
        chamadas.append((self.plataforma, "atualizar", external_id))

    def excluir(self, external_id):
        chamadas.append((self.plataforma, "excluir", external_id))


class EstoqueFalso(EnviadorRecurso):
    recurso = "estoque"
    modelo = VarianteProduto
    entidade = "variantes"

    def atualizar(self, obj, external_id):
        chamadas.append((self.plataforma, "estoque", obj.inventory_quantity))


class CategoriaFalsa(EnviadorRecurso):
    """So atualiza: criar cai no EnvioNaoSuportado da base."""

    recurso = "categorias"
    modelo = Categoria


class MarketplaceFalso(Marketplace):
    plataforma = "falso"
    recursos = (ProdutoFalso, EstoqueFalso, CategoriaFalsa)


class ShopifyFalso(MarketplaceFalso):
    plataforma = "shopify"


class ApiFora(RuntimeError):
    pass


def ligar(configuracao, recurso, *operacoes):
    matriz = configuracao.permissoes
    for operacao in operacoes:
        matriz.setdefault("enviar", {}).setdefault(recurso, {})[operacao] = True
    configuracao.permissoes = matriz
    configuracao.save()
    return configuracao


def configuracao(plataforma, recursos=("produtos", "estoque", "categorias")):
    config = ConfiguracaoIntegracao.objects.create(nome=plataforma.title(), plataforma=plataforma)
    for recurso in recursos:
        ligar(config, recurso, "create", "update", "delete")
    return config
