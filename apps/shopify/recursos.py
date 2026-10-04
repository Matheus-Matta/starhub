from decimal import Decimal, InvalidOperation

from django.utils.text import slugify

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Categoria, Cliente, Cupom, Pedido, Produto, VarianteProduto
from apps.shopify import categorias_imagem, produtos_dados
from apps.shopify.cupons import importar_desconto
from apps.shopify.imagens import sincronizar_imagens
from apps.shopify.produtos import atualizar_variantes, criar_variantes

MODELOS = {
    "produtos": Produto,
    "categorias": Categoria,
    "clientes": Cliente,
    "pedidos": Pedido,
    "cupons": Cupom,
}


def _decimal(valor):
    try:
        return Decimal(str(valor or "0"))
    except InvalidOperation:
        return Decimal("0")


def _existente(recurso, externo_id):
    referencia = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=recurso, external_id=externo_id
    ).first()
    modelo = MODELOS.get(recurso)
    return modelo.objects.filter(pk=referencia.object_id).first() if referencia and modelo else None


def _referenciar(recurso, externo_id, obj):
    ExternalReference.objects.get_or_create(
        platform=Origin.SHOPIFY,
        entity_type=recurso,
        external_id=externo_id,
        defaults={"object_id": str(obj.pk), "origin": Origin.SHOPIFY},
    )
    return obj


def produto(dados, sobrescrever=False):
    """Produto da loja no hub: cria o que falta e atualiza o que ja existe.

    `sobrescrever` e so da sincronizacao de importacao (sincronizar.py): ai a loja
    manda em tudo, nome incluido. Webhook, produto faltante de pedido e eco do envio
    seguem com o que o hub tem.

    Ja vinculado ou achado pelo slug, recebe os dados da loja (produtos_dados.py) e
    as variantes, nao so as imagens: senao SEO, tags e colecoes ficavam desatualizados.
    """
    externo_id = dados["id"]
    obj = _existente("produtos", externo_id)
    criado = False
    if obj is None:
        slug = slugify(dados.get("handle") or dados.get("title") or "produto")
        variantes = (dados.get("variants") or {}).get("nodes") or []
        obj, criado = Produto.objects.get_or_create(slug=slug, defaults={
            "nome": dados.get("title") or "Produto Shopify",
            "descricao": (dados.get("descriptionHtml") or dados.get("bodyHtml")
                          or dados.get("body_html") or ""),
            "fornecedor": dados.get("vendor") or "",
            "tipo": Produto.Tipo.VARIAVEL if len(variantes) > 1 else Produto.Tipo.SIMPLES,
            "origin": Origin.SHOPIFY,
        })
        obj = _referenciar("produtos", externo_id, obj)
    if criado:
        criar_variantes(obj, dados, _decimal)
    else:
        atualizar_variantes(obj, dados, _decimal, sobrescrever)
    produtos_dados.aplicar(obj, dados, sobrescrever and not criado)
    sincronizar_imagens(obj, dados)
    return obj, criado


def categoria(dados):
    externo_id = dados["id"]
    obj = _existente("categorias", externo_id)
    if obj:
        return obj, False
    nome = dados.get("title") or "Categoria Shopify"
    slug = slugify(dados.get("handle") or nome)
    imagem = dados.get("image") or None
    obj, criado = Categoria.objects.get_or_create(slug=slug, defaults={
        "nome": nome, "descricao": dados.get("descriptionHtml") or "",
        "origin": Origin.SHOPIFY,
    })
    obj = _referenciar("categorias", externo_id, obj)
    if obj.imagem:
        # Categoria do hub com foto propria, vinculada pelo slug: a do hub vale.
        categorias_imagem.registrar_importada(obj, imagem)
    else:
        # Baixa depois do vinculo, que e onde fica a origem do download.
        obj.imagem = categorias_imagem.recebida(obj, imagem)
        if obj.imagem:
            obj.save()
    return obj, criado


def cliente(dados):
    from apps.shopify.clientes import importar_cliente

    return importar_cliente(dados)


def pedido(dados):
    # Import tardio: pedidos.py usa _existente/_referenciar deste modulo.
    from apps.shopify.pedidos import importar_pedido

    return importar_pedido(dados)


def cupom(dados):
    return importar_desconto(dados)


def estoque(dados):
    sku = dados.get("sku") or ""
    variante = VarianteProduto.objects.filter(sku=sku).first() if sku else None
    if not variante:
        return None, False
    variante.inventory_quantity = dados.get("inventoryQuantity") or 0
    variante.save()
    return variante, False


SINCRONIZADORES = {
    "produtos": produto, "categorias": categoria, "clientes": cliente,
    "pedidos": pedido, "cupons": cupom, "estoque": estoque,
}


def desativar(recurso, externo_id):
    obj = _existente(recurso, externo_id)
    if obj is None:
        return False
    obj.active = False
    obj.save()
    return True
