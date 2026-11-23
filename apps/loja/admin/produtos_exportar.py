"""Colunas e linhas do Exportar da lista de produtos (core/relatorios/modelos.py).

A lista junta nome, SKU e foto numa celula so e mostra o variavel numa linha, com o
preco e o estoque da variante padrao. No Excel isso nao serve: cada dado precisa da sua
coluna (filtrar por SKU, somar estoque) e cada variacao da sua linha. A linha da
variacao e uma copia do produto que le a variante dela no lugar da padrao (o mesmo
jeito da API Woo, woo_api/recursos/produtos_variacao.py).
"""

import copy

from django.contrib import admin

from apps.loja.models import Produto, VarianteProduto


def _variante(produto):
    return produto.variante_padrao


class ExportarProdutoMixin:
    colunas_exportacao = [
        "exp_id", "nome", "exp_variacao", "exp_sku", "exp_barcode", "codigo_externo", "tipo",
        "exp_preco", "exp_promocional", "estoque", "exp_situacao", "status", "active",
        "updated_at",
    ]

    def linhas_da_exportacao(self, produto):
        if produto.tipo != Produto.Tipo.VARIAVEL:
            return [produto]
        linhas = []
        for variante in produto.variantes.all():
            linha = copy.copy(produto)
            linha._variante_padrao_cache = variante
            linhas.append(linha)
        return linhas or [produto]

    @admin.display(description="ID")
    def exp_id(self, produto):
        return produto.pk

    @admin.display(description="variacao")
    def exp_variacao(self, produto):
        variante = _variante(produto)
        return variante.titulo if variante and produto.tipo == Produto.Tipo.VARIAVEL else ""

    @admin.display(description="SKU")
    def exp_sku(self, produto):
        return produto.sku

    @admin.display(description="codigo de barras")
    def exp_barcode(self, produto):
        variante = _variante(produto)
        return variante.barcode if variante else ""

    @admin.display(description="preco")
    def exp_preco(self, produto):
        return produto.preco_regular

    @admin.display(description="preco promocional")
    def exp_promocional(self, produto):
        return produto.preco_promocional

    @admin.display(description="situacao do estoque")
    def exp_situacao(self, produto):
        return VarianteProduto.SituacaoEstoque(produto.situacao_estoque).label

    # Dinheiro no Excel como numero com "R$" (core/relatorios/modelos.py::_celula).
    exp_preco.em_reais = True
    exp_promocional.em_reais = True
