from apps.loja.models import VarianteProduto


def obter_variante_padrao(produto, **values):
    defaults = {"titulo": "Default", "is_default": True, **values}
    variante, created = VarianteProduto.objects.get_or_create(
        produto=produto, is_default=True, defaults=defaults
    )
    if not created and values:
        for field, value in values.items():
            setattr(variante, field, value)
        # save() completo: stock_status e calculado no save e ficaria de fora do update_fields.
        variante.save()
    return variante


def criar_produto(nome, **variante):
    """Produto simples com a variante padrao ja preenchida (sku, price, estoque...)."""
    from apps.loja.models import Produto

    produto = Produto.objects.create(nome=nome)
    if variante:
        produto._variante_padrao_cache = obter_variante_padrao(produto, **variante)
    return produto
