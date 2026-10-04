from decimal import Decimal, InvalidOperation

from django.utils.text import slugify

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.midias import sincronizar_midias
from apps.loja.services.slugs import slug_livre
from apps.loja.services.variantes import obter_variante_padrao
from apps.woo_api import datas, metadados
from apps.woo_api.erros import WooErro, parametro_invalido
from apps.woo_api.recursos.base import booleano, escolha, inteiro, texto
from apps.woo_api.recursos.termos import categorias_do_produto, tags_do_produto

PRODUCT_TEXT = {
    "name": ("nome", 255), "description": ("descricao", None),
    "short_description": ("descricao_curta", None), "external_url": ("url_externa", 200),
    "button_text": ("texto_botao", 100), "purchase_note": ("nota_compra", None),
}
PRODUCT_BOOL = {"featured": "destaque", "reviews_allowed": "avaliacoes_permitidas"}
PRODUCT_CHOICE = {
    "type": ("tipo", Produto.Tipo), "status": ("status", Produto.Status),
    "catalog_visibility": ("visibilidade", Produto.Visibilidade),
}
VARIANT_BOOL = {
    "manage_stock": "manage_inventory", "sold_individually": "sold_individually",
    "virtual": "virtual", "downloadable": "downloadable",
}


def _money(data, field):
    try:
        return dinheiro(data[field])
    except ValorInvalido as error:
        raise parametro_invalido(field, str(error)) from error


def _decimal(value, field):
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except InvalidOperation as error:
        raise parametro_invalido(field, f"{field} nao e um decimal.") from error


def erro_sku(sku, id_existente=None):
    data = {"unique_sku": sku}
    if id_existente:
        data["resource_id"] = id_existente
    return WooErro("product_invalid_sku", "SKU invalido ou repetido.", 400, data)


def _product_fields(product, data):
    for field, (attribute, size) in PRODUCT_TEXT.items():
        if field in data:
            setattr(product, attribute, texto(data[field], field, size))
    for field, attribute in PRODUCT_BOOL.items():
        if field in data:
            setattr(product, attribute, booleano(data[field], field))
    for field, (attribute, choices) in PRODUCT_CHOICE.items():
        if field in data:
            setattr(product, attribute, escolha(data[field], field, choices.values))
    if "attributes" in data:
        if not isinstance(data["attributes"], list):
            raise parametro_invalido("attributes", "attributes nao e do tipo array.")
        product.atributos = data["attributes"]
    if "meta_data" in data:
        product.metadados = metadados.mesclar(product.metadados, data["meta_data"])


def _variant_fields(variant, data):
    for field, attribute in VARIANT_BOOL.items():
        if field in data:
            setattr(variant, attribute, booleano(data[field], field))
    if "regular_price" in data:
        variant.price = _money(data, "regular_price")
    if "sale_price" in data:
        variant.sale_price = _money(data, "sale_price")
    if "stock_quantity" in data:
        variant.inventory_quantity = inteiro(data["stock_quantity"], "stock_quantity", True) or 0
    if "low_stock_amount" in data:
        variant.low_stock_amount = inteiro(data["low_stock_amount"], "low_stock_amount", True)
    if "sku" in data:
        sku = texto(data["sku"], "sku", 100).strip()
        existing = None
        if sku:
            existing = VarianteProduto.objects.filter(sku=sku).exclude(pk=variant.pk).first()
        if existing:
            raise erro_sku(sku, existing.produto_id)
        variant.sku = sku
    if "stock_status" in data:
        variant.stock_status = escolha(
            data["stock_status"], "stock_status", VarianteProduto.SituacaoEstoque.values
        )
    if "backorders" in data:
        backorders = escolha(data["backorders"], "backorders", ["no", "notify", "yes"])
        variant.inventory_policy = "deny" if backorders == "no" else "continue"
    for field, attribute, size in (
        ("tax_class", "tax_class", 100), ("shipping_class", "shipping_class", 100),
    ):
        if field in data:
            setattr(variant, attribute, texto(data[field], field, size))
    if "tax_status" in data:
        variant.tax_status = escolha(
            data["tax_status"], "tax_status", VarianteProduto.SituacaoFiscal.values
        )
        variant.taxable = variant.tax_status != "none"
    if "weight" in data:
        variant.weight = _decimal(data["weight"], "weight") if data["weight"] else None
    if "dimensions" in data:
        if not isinstance(data["dimensions"], dict):
            raise parametro_invalido("dimensions", "dimensions nao e do tipo object.")
        variant.dimensions = {key: str(value) for key, value in data["dimensions"].items()
                              if key in ("length", "width", "height")}
    for prefix, attribute in (
        ("date_on_sale_from", "sale_starts_at"), ("date_on_sale_to", "sale_ends_at")
    ):
        if prefix in data or f"{prefix}_gmt" in data:
            setattr(variant, attribute, datas.ler_do_corpo(data, prefix))


def _relations(product, data, variant):
    if "categories" in data:
        product.categorias.set(categorias_do_produto(data))
    if "tags" in data:
        product.tags.set(tags_do_produto(data))
    if "images" in data:
        if not isinstance(data["images"], list):
            raise parametro_invalido("images", "images nao e do tipo array.")
        # A galeria do produto no Woo e a da variante padrao (a 1a imagem e a capa).
        # O "id" que o ERP devolve e o da nossa midia: com ele a imagem e mantida.
        imagens = [
            {"id": item.get("id"), "src": item.get("src", ""), "alt": item.get("alt", "")}
            for item in data["images"] if isinstance(item, dict) and item.get("src")
        ]
        product.midias.filter(variante__isnull=True).delete()
        sincronizar_midias(variant, imagens)


def gravar_produto(product, data, creating):
    _product_fields(product, data)
    if data.get("slug"):
        product.slug = slugify(str(data["slug"]), allow_unicode=True)
    elif creating or not product.slug:
        # Dois produtos com o mesmo nome: o segundo ganha "-2" em vez de estourar o indice.
        product.slug = slug_livre(Produto, product.nome, product.pk)
    if "menu_order" in data:
        product.ordem_menu = inteiro(data["menu_order"], "menu_order")
    if "parent_id" in data:
        product.id_pai = inteiro(data["parent_id"], "parent_id")
    product.save()
    variant = obter_variante_padrao(product)
    _variant_fields(variant, data)
    variant.save()
    _relations(product, data, variant)
    if creating and (data.get("date_created") or data.get("date_created_gmt")):
        product.created_at = datas.ler_do_corpo(data, "date_created")
        Produto.objects.filter(pk=product.pk).update(created_at=product.created_at)
    return product
