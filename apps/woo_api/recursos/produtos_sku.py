"""Produto da v3 achado pelo SKU: o ERP manda id 0 quando nao sabe o id do hub.

Um "criar" com SKU que o hub conhece vira atualizacao de preco e estoque daquela
variante (e devolve o produto, com o id que o ERP guarda). SKU que o hub nao tem vira
um produto simples INATIVO, em rascunho, so com o essencial (nome, SKU, precos e
estoque): inativo nao vai a loja nenhuma (loja/services/inativos.py) ate o operador
completar e ativar. No PUT, o SKU escolhe a variante dentro do produto da URL, porque
o id do pai sozinho so alcanca a variante padrao.

    variante_do_sku({"sku": "7656"})               # qualquer produto (criar)
    variante_do_sku({"sku": "7656"}, produto=obj)  # so dentro de obj (PUT)
"""

import logging

from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.slugs import slug_livre
from apps.loja.services.variantes import obter_variante_padrao
from apps.woo_api.erros import WooErro
from apps.woo_api.recursos.base import texto
from apps.woo_api.recursos.produtos_entrada import _variant_fields

logger = logging.getLogger("django.request")


def sku_de(dados):
    return texto(dados.get("sku") or "", "sku", 100).strip()


def variante_do_sku(dados, produto=None):
    """Variante travada (select_for_update) e relida depois do lock, ou None."""
    sku = sku_de(dados)
    if not sku:
        return None
    variantes = VarianteProduto.objects.select_for_update().filter(sku=sku).exclude(
        produto__status=Produto.Status.LIXEIRA)
    if produto is not None:
        variantes = variantes.filter(produto=produto)
    return variantes.first()


def gravar_na_variante(variante, permitidos):
    _variant_fields(variante, permitidos)
    variante.save()  # save() completo: stock_status e calculado nele
    logger.info("Woo v3 localizou o produto %s pelo SKU %s", variante.produto_id, variante.sku)
    return Produto.objects.get(pk=variante.produto_id)


def criar_inativo(produto, dados, permitidos):
    """`produto` e o Produto novo (sem pk) que a view montou; SKU repetido ao mesmo
    tempo e barrado pelo indice unico do SKU (erro_integridade da API: 400)."""
    sku = sku_de(dados)
    produto.nome = texto(dados.get("name") or "", "name", 255).strip() or f"Produto {sku}"
    produto.tipo, produto.status = Produto.Tipo.SIMPLES, Produto.Status.RASCUNHO
    produto.active = False  # antes do 1o save: o Distribuidor nao manda nada as lojas
    produto.slug = slug_livre(Produto, produto.nome)
    produto.save()
    variante = obter_variante_padrao(produto)
    _variant_fields(variante, {**permitidos, "sku": sku})
    variante.save()
    logger.info("Woo v3 criou o produto %s inativo para o SKU %s", produto.pk, sku)
    return produto


def erro_sem_sku():
    return WooErro("rest_no_route", "Produtos da API v3 so sao criados com sku: envie o sku "
                   "do produto (ou o id dele na URL para atualizar).", 404)
