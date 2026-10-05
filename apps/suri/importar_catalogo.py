"""Categorias e produtos do Suri Shop no catalogo do hub.

    importar_categorias(cliente.get("shop/categories"))   # arvore: categoria > children
    produto, criado = importar_produto(json_do_produto_suri)

Produto do Suri: preco e estoque ficam em `dimensions` (uma por SKU). Sem `attributes`
o produto e simples (uma dimensao); com eles, variavel, e cada dimensao vira uma
variante com as opcoes de `dimensions` ({"Cor": "Azul", "Tamanho": "M"}). Estoque por
loja do Suri: o hub tem um numero so, a soma das lojas. Peso vem em gramas.
"""

from decimal import Decimal

from django.db import transaction
from django.utils.text import slugify

from apps.core.imagens_remotas import ImagemErro, baixar
from apps.core.models import Origin
from apps.loja.dinheiro import ZERO, dinheiro
from apps.loja.models import Categoria, MidiaProduto, Produto, VarianteProduto
from apps.loja.services.midias import sincronizar_midias
from apps.loja.services.slugs import slug_livre
from apps.loja.services.variantes import obter_variante_padrao
from apps.suri import vinculos
from apps.suri.contexto import avisar
from apps.suri.opcoes import gravar_opcoes

ORIGEM = Origin.SURI


def valor(numero):
    return dinheiro(numero) if numero not in (None, "") else None


def importar_categorias(arvore, pai=None):
    """Cria/atualiza a arvore inteira; devolve {id do Suri: Categoria}."""
    mapa = {}
    for dados in arvore or []:
        obj = vinculos.existente("categorias", Categoria, dados["id"])
        if obj is None:
            slug = slugify(dados.get("name") or "", allow_unicode=True)
            obj = Categoria.objects.filter(slug=slug).first() if slug else None
            obj = obj or Categoria(slug=slug_livre(Categoria, slug or "categoria"), origin=ORIGEM)
        obj.nome = (dados.get("name") or obj.nome or "Categoria Suri")[:200]
        obj.descricao = dados.get("description") or obj.descricao
        obj.pai = pai if pai is not None else obj.pai
        obj.save()
        vinculos.referenciar("categorias", dados["id"], obj)
        mapa[str(dados["id"])] = obj
        mapa |= importar_categorias(dados.get("children"), obj)
    return mapa


def _estoque(dimensao):
    lojas = (dimensao.get("stocks") or {}).values()
    return int(sum((loja or {}).get("stock") or 0 for loja in lojas))


def _sku_livre(variante, sku, produto_dados):
    """SKU de outra variante do hub nao entra: avisa e mantem o da variante."""
    if not sku or sku == variante.sku:
        return
    if VarianteProduto.objects.filter(sku=sku).exclude(pk=variante.pk).exists():
        avisar(f"SKU {sku} do Suri ja e de outra variante no hub; mantido o "
               f"{variante.sku or 'vazio'}.", recurso="produtos", id=variante.produto_id,
               descricao=variante.produto.nome, id_externo=produto_dados.get("id"))
        return
    variante.sku = sku


def _gravar_variante(variante, dimensao, produto_dados, posicao, completa):
    preco = valor(dimensao.get("price"))
    variante.price = preco if preco is not None else valor(produto_dados.get("price")) or ZERO
    promocional = valor(produto_dados.get("promotionalPrice"))
    variante.sale_price = promocional if promocional and promocional < variante.price else None
    variante.inventory_quantity = _estoque(dimensao)
    variante.posicao = posicao
    gramas = (dimensao.get("measurements") or {}).get("weightInGrams")
    if gramas:
        variante.weight = Decimal(str(gramas)) / 1000  # o hub guarda em kg
    if completa:
        _sku_livre(variante, str(dimensao.get("sku") or "").strip()[:100], produto_dados)
        opcoes = dimensao.get("dimensions") or {}
        variante.titulo = (" / ".join(str(v) for v in opcoes.values()) or "Default")[:255]
    variante.save()
    gravar_opcoes(variante, dimensao.get("dimensions"))


def _variantes(produto, dados, completa):
    externo = str(dados["id"])
    variavel = bool(dados.get("attributes"))
    for posicao, dimensao in enumerate(dados.get("dimensions") or [{"sku": dados.get("sku")}]):
        chave = vinculos.id_variacao(externo, dimensao.get("sku"))
        variante = vinculos.existente("variantes", VarianteProduto, chave)
        if variante is None and not variavel:
            variante = produto.variante_padrao or obter_variante_padrao(produto)
        if variante is None and dimensao.get("sku"):
            variante = produto.variantes.filter(sku=dimensao["sku"]).first()
        nova = variante is None
        variante = variante or VarianteProduto(produto=produto, origin=ORIGEM,
                                               is_default=not produto.variantes.exists())
        _gravar_variante(variante, dimensao, dados, posicao, completa or nova)
        vinculos.referenciar("variantes", chave, variante, pai=externo)


def _imagens(produto, dados):
    """Foto ja baixada (vinculo "midias" pela URL do Suri) nao baixa de novo."""
    lista = []
    for imagem in dados.get("images") or []:
        url = (imagem.get("url") or "").strip()
        if not url:
            continue
        midia = vinculos.existente("midias", MidiaProduto, url)
        if midia is not None:
            lista.append({"id": midia.pk, "src": midia.url, "alt": midia.alt_text, "_url": url})
            continue
        try:
            lista.append({"id": None, "src": baixar(url), "alt": imagem.get("description") or "",
                          "_url": url})
        except ImagemErro as erro:
            avisar(f"Imagem nao importada: {erro}", recurso="produtos", id=produto.pk,
                   descricao=produto.nome, id_externo=dados.get("id"))
    padrao = produto.variantes.filter(is_default=True).first() or produto.variantes.first()
    if not padrao or not lista:
        return
    sincronizar_midias(padrao, [{k: v for k, v in i.items() if k != "_url"} for i in lista])
    for midia, item in zip(padrao.midias.order_by("posicao", "id"), lista, strict=False):
        vinculos.referenciar("midias", item["_url"], midia)


def _categorias(produto, dados):
    ids = [dados.get("categoryId"), dados.get("subcategoryId")]
    categorias = [c for c in (vinculos.existente("categorias", Categoria, i) for i in ids if i)
                  if c]
    if categorias:
        produto.categorias.set(categorias)


@transaction.atomic
def importar_produto(dados, sobrescrever=False):
    """Produto novo recebe tudo; o existente so preco e estoque, salvo `sobrescrever`."""
    externo = str(dados["id"])
    obj = vinculos.existente("produtos", Produto, externo)
    criado = obj is None
    if criado:
        obj = Produto(slug=slug_livre(Produto, slugify(dados.get("name") or "produto")),
                      origin=ORIGEM)
    if criado or sobrescrever:
        obj.nome = (dados.get("name") or "Produto Suri")[:255]
        obj.descricao = dados.get("description") or ""
        obj.tipo = Produto.Tipo.VARIAVEL if dados.get("attributes") else Produto.Tipo.SIMPLES
        ativo = dados.get("isActive", True)
        obj.status = Produto.Status.PUBLICADO if ativo else Produto.Status.RASCUNHO
        obj.save()
    vinculos.referenciar("produtos", externo, obj)
    _categorias(obj, dados)
    _variantes(obj, dados, criado or sobrescrever)
    _imagens(obj, dados)
    return obj, criado
