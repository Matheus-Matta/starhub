"""Produto da loja WooCommerce no catalogo do hub (simples ou variavel).

    produto, criado = importar_produto(dados_do_produto, variacoes=[...])

`variacoes` sao as de GET products/<id>/variations (o produto variavel so traz os ids).
`sobrescrever` e so da sincronizacao de importacao: ai a loja manda em nome, descricao,
titulo e SKU. Webhook e eco do envio atualizam preco, estoque e logistica, nao o texto
que o lojista pode ter ajustado no hub.
"""

from django.db import transaction
from django.utils.text import slugify

from apps.loja.models import (
    Produto,
    TipoVariante,
    ValorDaVarianteProduto,
    ValorVariante,
    VarianteProduto,
)
from apps.loja.services.midias import sincronizar_midias
from apps.loja.services.slugs import slug_livre
from apps.loja.services.variantes import obter_variante_padrao
from apps.woocommerce import vinculos
from apps.woocommerce.contexto import avisar
from apps.woocommerce.imagens import imagens_locais, vincular_midias
from apps.woocommerce.importar_catalogo import (
    ORIGEM,
    campos_variante,
    categorias_do_produto,
    tags_do_produto,
)

TEXTOS = {"name": "nome", "description": "descricao", "short_description": "descricao_curta"}


def _escolha(valor, opcoes, atual):
    return valor if valor in opcoes.values else atual


def _textos(obj, dados):
    for campo, atributo in TEXTOS.items():
        if dados.get(campo) is not None:
            setattr(obj, atributo, str(dados[campo])[:255] if atributo == "nome" else dados[campo])
    obj.tipo = _escolha(dados.get("type"), Produto.Tipo, obj.tipo)
    obj.status = _escolha(dados.get("status"), Produto.Status, obj.status)
    obj.visibilidade = _escolha(dados.get("catalog_visibility"), Produto.Visibilidade,
                                obj.visibilidade)
    if isinstance(dados.get("featured"), bool):
        obj.destaque = dados["featured"]


def _pelo_sku(dados):
    sku = (dados.get("sku") or "").strip()
    variante = VarianteProduto.objects.filter(sku=sku).select_related("produto").first() \
        if sku else None
    return variante.produto if variante else None


def _sku_livre(variante, sku, produto_externo):
    """SKU de outra variante do hub nao entra: avisa e mantem o da variante."""
    if not sku or sku == variante.sku:
        return
    if VarianteProduto.objects.filter(sku=sku).exclude(pk=variante.pk).exists():
        avisar(f"SKU {sku} da loja ja e de outra variante no hub; mantido o "
               f"{variante.sku or 'vazio'}.", recurso="produtos", id=variante.produto_id,
               descricao=variante.produto.nome, id_externo=produto_externo)
        return
    variante.sku = sku


def _opcoes(variante, atributos):
    for posicao, atributo in enumerate(atributos or []):
        nome, texto = atributo.get("name"), str(atributo.get("option") or "").strip()
        if not nome or not texto:
            continue
        tipo = (TipoVariante.objects.filter(nome__iexact=nome).first()
                or TipoVariante.objects.create(nome=nome, posicao=posicao, origin=ORIGEM))
        valor = (ValorVariante.objects.filter(tipo=tipo, valor_normalizado=texto.casefold())
                 .first() or ValorVariante.objects.create(tipo=tipo, valor=texto,
                                                          posicao=posicao, origin=ORIGEM))
        ValorDaVarianteProduto.objects.get_or_create(variante=variante, valor=valor,
                                                     defaults={"origin": ORIGEM})


def _gravar_variante(variante, dados, posicao, completa, produto_externo):
    for campo, valor in campos_variante(dados, posicao).items():
        setattr(variante, campo, valor)
    if completa:
        _sku_livre(variante, (dados.get("sku") or "").strip(), produto_externo)
        nomes = [str(a.get("option")) for a in dados.get("attributes") or [] if a.get("option")]
        variante.titulo = (" / ".join(nomes) or variante.titulo or "Default")[:255]
    variante.save()


def _variacoes(produto, variacoes, completa, produto_externo):
    for posicao, dados in enumerate(variacoes):
        variante = vinculos.existente("variantes", VarianteProduto, dados["id"])
        if variante is None and dados.get("sku"):
            variante = produto.variantes.filter(sku=dados["sku"]).first()
        nova = variante is None
        variante = variante or VarianteProduto(produto=produto, origin=ORIGEM,
                                               is_default=not produto.variantes.exists())
        _gravar_variante(variante, dados, posicao, completa or nova, produto_externo)
        vinculos.referenciar("variantes", dados["id"], variante, pai=produto_externo)
        _opcoes(variante, dados.get("attributes"))
        if dados.get("image"):
            lista = imagens_locais(produto, [dados["image"]])
            sincronizar_midias(variante, [{k: v for k, v in i.items() if k != "_woo_id"}
                                          for i in lista])
            vincular_midias(variante, lista)


@transaction.atomic
def importar_produto(dados, variacoes=None, sobrescrever=False):
    externo = dados["id"]
    obj = vinculos.existente("produtos", Produto, externo) or _pelo_sku(dados)
    criado = obj is None
    if criado:
        base = dados.get("slug") or slugify(dados.get("name") or "produto")
        obj = Produto(slug=slug_livre(Produto, base), origin=ORIGEM)
    if criado or sobrescrever:
        _textos(obj, dados)
        obj.nome = obj.nome or "Produto WooCommerce"
        obj.save()
    vinculos.referenciar("produtos", externo, obj)
    if "categories" in dados:
        obj.categorias.set(categorias_do_produto(dados["categories"]))
    if "tags" in dados:
        obj.tags.set(tags_do_produto(dados["tags"]))
    if dados.get("type") == Produto.Tipo.VARIAVEL and variacoes:
        _variacoes(obj, variacoes, criado or sobrescrever, externo)
    else:
        padrao = obj.variante_padrao or obter_variante_padrao(obj)
        _gravar_variante(padrao, dados, 0, criado or sobrescrever, externo)
    lista = imagens_locais(obj, dados.get("images"))
    padrao = obj.variantes.filter(is_default=True).first() or obj.variantes.first()
    if padrao and lista:
        sincronizar_midias(padrao, [{k: v for k, v in i.items() if k != "_woo_id"}
                                    for i in lista])
        vincular_midias(padrao, lista)
    return obj, criado
