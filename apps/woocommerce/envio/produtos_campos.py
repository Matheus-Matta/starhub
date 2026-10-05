"""Campos do produto do hub no formato da API do WooCommerce.

Dinheiro vai como texto ("19.90"), como o Woo espera. Campo de variante (preco,
estoque, SKU, peso) e o mesmo no produto simples e na variacao.
"""

from apps.loja.dinheiro import texto
from apps.loja.models import Produto
from apps.woocommerce import vinculos

TIPOS = {Produto.Tipo.SIMPLES, Produto.Tipo.VARIAVEL, Produto.Tipo.AGRUPADO,
         Produto.Tipo.EXTERNO}
# Arquivado e lixeira nao existem como status de produto no Woo: ficam como rascunho.
STATUS = {Produto.Status.PUBLICADO, Produto.Status.RASCUNHO, Produto.Status.PENDENTE,
          Produto.Status.PRIVADO}


def campos_variante(variante):
    campos = {"sku": variante.sku, "regular_price": texto(variante.price),
              "sale_price": texto(variante.sale_price),
              "manage_stock": variante.manage_inventory,
              "backorders": "no" if variante.inventory_policy == "deny" else "notify"}
    if variante.manage_inventory:
        campos["stock_quantity"] = variante.inventory_quantity
    else:
        campos["stock_status"] = variante.stock_status
    if variante.weight is not None:
        campos["weight"] = str(variante.weight)
    return campos


def categorias(produto):
    ids = (vinculos.externo_id("categorias", c.pk) for c in produto.categorias.all())
    return [{"id": int(i)} for i in ids if i]


def atributos(produto):
    """Opcoes das variantes (Cor: Azul, Verde) como atributos de variacao do Woo."""
    opcoes = {}
    for variante in produto.variantes.all():
        for opcao in variante.opcoes.select_related("valor__tipo"):
            valores = opcoes.setdefault(opcao.valor.tipo.nome, [])
            if opcao.valor.valor not in valores:
                valores.append(opcao.valor.valor)
    return [{"name": nome, "options": valores, "variation": True, "visible": True}
            for nome, valores in opcoes.items()]


def corpo_produto(produto):
    tipo = produto.tipo if produto.tipo in TIPOS else Produto.Tipo.SIMPLES
    corpo = {"name": produto.nome, "slug": produto.slug, "type": tipo,
             "status": produto.status if produto.status in STATUS else "draft",
             "featured": produto.destaque, "catalog_visibility": produto.visibilidade,
             "description": produto.descricao, "short_description": produto.descricao_curta,
             "categories": categorias(produto)}
    if tipo == Produto.Tipo.VARIAVEL:
        corpo["attributes"] = atributos(produto)
    elif produto.variante_padrao is not None:
        corpo |= campos_variante(produto.variante_padrao)
    return corpo


def corpo_variacao(variante):
    corpo = campos_variante(variante)
    corpo["attributes"] = [{"name": o.valor.tipo.nome, "option": o.valor.valor}
                           for o in variante.opcoes.select_related("valor__tipo")]
    return corpo
