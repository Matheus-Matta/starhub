"""Produto do hub no formato do Suri Shop (o PUT do Suri substitui o objeto inteiro).

    {"id", "sku", "categoryId", "subcategoryId", "isActive", "name", "description",
     "price", "promotionalPrice", "images": [{"url"}], "attributes": [{"name", "options"}],
     "dimensions": [{"sku", "dimensions": {"Cor": "Azul"}, "price",
                     "stocks": {"<loja>": {"stock": 3}}, "measurements": {...}}]}

Preco e Decimal ate o JSON (apps/suri/cliente._json escreve o numero exato).
"""

from decimal import Decimal

from apps.integracoes.url_publica import url_publica
from apps.loja.dinheiro import ZERO
from apps.loja.models import MidiaProduto, Produto
from apps.suri.cliente import SuriErro
from apps.suri.envio.base import id_no_suri


def _opcoes(variante):
    opcoes = variante.opcoes.select_related("valor__tipo")
    return {o.valor.tipo.nome: o.valor.valor for o in opcoes}


def _atributos(variantes):
    atributos = {}
    for variante in variantes:
        for nome, valor in _opcoes(variante).items():
            opcoes = atributos.setdefault(nome, [])
            if {"name": valor} not in opcoes:
                opcoes.append({"name": valor})
    return [{"name": nome, "options": opcoes} for nome, opcoes in atributos.items()]


def _dimensao(variante, produto_id, loja):
    dimensao = {"sku": variante.sku or f"{produto_id}-{variante.pk}",
                "dimensions": _opcoes(variante), "price": variante.price or ZERO,
                "stocks": {loja: {"stock": max(variante.inventory_quantity, 0)}}}
    if variante.weight:
        gramas = (Decimal(variante.weight) * 1000).to_integral_value()  # o hub guarda em kg
        dimensao["measurements"] = {"weightInGrams": gramas, "unitsPerPackage": 1}
    return dimensao


def categorias(enviador_categorias, produto):
    """(categoryId, subcategoryId): o Suri exige a categoria, e ela vai antes se faltar."""
    categoria = produto.categorias.order_by("pai_id", "id").first()
    if categoria is None:
        raise SuriErro(f"Produto {produto.pk} sem categoria: o Suri exige uma. Ponha o "
                       "produto numa categoria no hub e salve de novo.")
    externo = enviador_categorias.garantir(categoria)
    if categoria.pai_id:
        return enviador_categorias.garantir(categoria.pai), externo
    return externo, None


def corpo(enviador_categorias, produto, loja, configuracao):
    produto_id = id_no_suri("produtos", produto)
    variantes = list(produto.variantes.order_by("posicao", "id"))
    padrao = produto.variante_padrao
    categoria, subcategoria = categorias(enviador_categorias, produto)
    imagens = [{"url": url, "description": m.alt_text or None}
               for m in produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao")
               if (url := url_publica(configuracao, m.url))]
    promocional = padrao.sale_price if padrao and padrao.sale_price else ZERO
    corpo = {
        "id": produto_id, "sku": (padrao.sku if padrao else "") or produto_id,
        "categoryId": categoria, "subcategoryId": subcategoria, "sellerId": "all",
        "isActive": produto.active and produto.status == Produto.Status.PUBLICADO,
        "name": produto.nome, "description": produto.descricao or "",
        "price": padrao.price if padrao else ZERO, "promotionalPrice": promocional,
        "hasShippingRestriction": False,
        "attributes": _atributos(variantes) if produto.tipo == Produto.Tipo.VARIAVEL else [],
        "dimensions": [_dimensao(v, produto_id, loja) for v in variantes],
    }
    if imagens:
        # "images": null apaga as fotos no Suri: sem foto publica no hub, a chave nem vai.
        corpo["images"] = imagens
    return corpo
