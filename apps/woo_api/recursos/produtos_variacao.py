"""Variacao de produto variavel na API Woo, com id proprio.

No Woo a variacao tem id proprio: GET products?sku=<sku da variacao> devolve a
variacao e PUT products/<id dela> altera so ela. O ERP guarda esse id. Antes o hub
devolvia o id do PAI, e o PUT seguinte caia na variante padrao: a variacao pedida
nao mudava e a padrao ficava com o preco e o estoque dela.

Produto e variante tem sequencias de id separadas no hub (o 7 pode ser os dois), entao
o id da variacao na API e BASE_VARIACAO + id da variante. A variante padrao segue com o
id do produto: produto simples e id que o ERP ja guardou nao mudam.

    id_woo(variante)                  # 7 (padrao) ou 1000000042
    variante_do_id(1000000042)        # VarianteProduto 42, ou None
    marcar(produto, variante)         # produto que a API mostra como a variacao
"""

import copy

from apps.loja.models import VarianteProduto
from apps.woo_api.recursos.produtos_saida import produto_para_woo

BASE_VARIACAO = 1_000_000_000


def id_woo(variante):
    return variante.produto_id if variante.is_default else BASE_VARIACAO + variante.pk


def variante_do_id(pk, travar=False):
    try:
        numero = int(pk)
    except (TypeError, ValueError):
        return None
    if numero <= BASE_VARIACAO:
        return None
    variantes = VarianteProduto.objects.filter(pk=numero - BASE_VARIACAO, is_default=False)
    return (variantes.select_for_update() if travar else variantes).first()


def marcar(produto, variante):
    """A variante padrao e o proprio produto; as outras saem como variacao."""
    produto._variacao = None if variante is None or variante.is_default else variante
    return produto


def variacao_de(produto):
    return getattr(produto, "_variacao", None)


def _opcoes(variante):
    return [{"id": 0, "name": item.valor.tipo.nome, "option": item.valor.valor}
            for item in variante.opcoes.select_related("valor__tipo")]


def variacao_para_woo(produto, variante, request=None):
    """O JSON do produto com preco, estoque, SKU e logistica da variacao (tudo isso o
    produto le da variante padrao: a copia troca a padrao pela variacao)."""
    copia = copy.copy(produto)
    copia._variante_padrao_cache = variante
    dados = produto_para_woo(copia, request)
    dados.update({
        "id": id_woo(variante), "name": f"{produto.nome} - {variante.titulo}",
        "type": "variation", "parent_id": produto.pk, "attributes": _opcoes(variante),
        "variations": [],
    })
    return dados


def linhas_por_sku(produto, skus, request=None):
    """GET ?sku=: cada SKU pedido vira a sua linha, como no Woo (a variacao, nao o pai)."""
    variantes = sorted((v for v in produto.variantes.all() if v.sku in skus),
                       key=lambda v: (not v.is_default, v.posicao, v.pk))
    if not variantes:
        return [produto_para_woo(produto, request)]
    return [produto_para_woo(produto, request) if v.is_default
            else variacao_para_woo(produto, v, request) for v in variantes]
