"""Produto -> JSON identico ao GET /wp-json/wc/v1/products/<id> do WooCommerce."""

from apps.loja.dinheiro import texto as dinheiro_texto
from apps.woo_api import datas

DIMENSOES_VAZIAS = {"length": "", "width": "", "height": ""}


def _categorias(produto):
    return [{"id": c.pk, "name": c.nome, "slug": c.slug} for c in produto.categorias.all()]


def _peso(valor):
    """A coluna tem 3 casas; o Woo devolve o peso como foi digitado: "20", nao "20.000"."""
    return "" if valor is None else format(valor.normalize(), "f")


def url_absoluta(src, request):
    """Imagem enviada pelo admin fica como "/media/..."; o ERP precisa da URL inteira."""
    if request is not None and src and src.startswith("/"):
        return request.build_absolute_uri(src)
    return src


def _imagens(produto, request):
    imagens = []
    for posicao, imagem in enumerate(produto.imagens or []):
        imagens.append({
            "id": imagem.get("id", posicao + 1),
            "date_created": imagem.get("date_created"),
            "date_created_gmt": imagem.get("date_created_gmt"),
            "date_modified": imagem.get("date_modified"),
            "date_modified_gmt": imagem.get("date_modified_gmt"),
            "src": url_absoluta(imagem.get("src", ""), request),
            "name": imagem.get("name", ""),
            "alt": imagem.get("alt", ""),
        })
    return imagens


def produto_para_woo(produto, request=None):
    variante = produto.variante_padrao
    if produto.tipo == produto.Tipo.BUNDLE:
        controla_estoque = produto.estoque is not None
    else:
        controla_estoque = bool(variante and variante.manage_inventory)
    preco = produto.preco
    permalink = request.build_absolute_uri(f"/produto/{produto.slug}/") if request else ""
    return {
        "id": produto.pk,
        "name": produto.nome,
        "slug": produto.slug,
        "permalink": permalink,
        **datas.par("date_created", produto.created_at),
        **datas.par("date_modified", produto.updated_at),
        "type": produto.tipo,
        "status": produto.status,
        "featured": produto.destaque,
        "catalog_visibility": produto.visibilidade,
        "description": produto.descricao,
        "short_description": produto.descricao_curta,
        "sku": produto.sku,
        "price": dinheiro_texto(preco),
        "regular_price": dinheiro_texto(produto.preco_regular),
        "sale_price": dinheiro_texto(produto.preco_promocional),
        **datas.par("date_on_sale_from", variante.sale_starts_at if variante else None),
        **datas.par("date_on_sale_to", variante.sale_ends_at if variante else None),
        "price_html": "",
        "on_sale": bool(
            variante and variante.sale_price is not None and preco == variante.sale_price
        ),
        "purchasable": preco is not None and produto.status != "trash",
        "total_sales": produto.total_vendas,
        "virtual": variante.virtual if variante else False,
        "downloadable": variante.downloadable if variante else False,
        "downloads": [],
        "download_limit": -1,
        "download_expiry": -1,
        "external_url": produto.url_externa,
        "button_text": produto.texto_botao,
        "tax_status": variante.tax_status if variante else "taxable",
        "tax_class": variante.tax_class if variante else "",
        # Bundle: estoque calculado pelos componentes (o que acaba primeiro limita).
        "manage_stock": controla_estoque,
        "stock_quantity": produto.estoque if controla_estoque else None,
        "stock_status": produto.situacao_estoque,
        "backorders": "yes" if variante and variante.inventory_policy == "continue" else "no",
        "backorders_allowed": bool(variante and variante.inventory_policy == "continue"),
        "backordered": produto.situacao_estoque == "onbackorder",
        "low_stock_amount": variante.low_stock_amount if variante else None,
        "sold_individually": variante.sold_individually if variante else False,
        "weight": _peso(variante.weight if variante else None),
        "dimensions": {**DIMENSOES_VAZIAS, **(variante.dimensions if variante else {})},
        "shipping_required": variante.requires_shipping if variante else True,
        "shipping_taxable": bool(variante and variante.tax_status in ("taxable", "shipping")),
        "shipping_class": variante.shipping_class if variante else "",
        "shipping_class_id": 0,
        "reviews_allowed": produto.avaliacoes_permitidas,
        "average_rating": "0.00",
        "rating_count": 0,
        "related_ids": [],
        "upsell_ids": [],
        "cross_sell_ids": [],
        "parent_id": produto.id_pai,
        "purchase_note": produto.nota_compra,
        "categories": _categorias(produto),
        "tags": [{"id": tag.pk, "name": tag.nome, "slug": tag.slug}
                 for tag in produto.tags.all()],
        "images": _imagens(produto, request),
        "attributes": produto.atributos or [],
        "default_attributes": [],
        "variations": [],
        "grouped_products": [],
        "menu_order": produto.ordem_menu,
        "meta_data": produto.metadados or [],
    }
