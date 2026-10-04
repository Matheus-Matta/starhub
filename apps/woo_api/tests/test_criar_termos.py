from decimal import Decimal

from apps.core.models import Origin
from apps.loja.models import Categoria, Cupom, Tag
from apps.loja.services.variantes import criar_produto
from apps.woo_api.tests.conftest import criar_pedido

PRODUTOS = "/wp-json/wc/v1/products"


def test_categoria_pelo_nome_e_criada_quando_nao_existe(api):
    """O ERP manda so o nome; antes a categoria era ignorada e o produto ficava sem ela."""
    corpo = api.post(PRODUTOS, {"name": "Camiseta", "categories": [{"name": "Roupas"}]},
                     format="json").json()
    categoria = Categoria.objects.get()
    assert (categoria.nome, categoria.slug, categoria.origin) == ("Roupas", "roupas", Origin.API)
    assert corpo["categories"] == [{"id": categoria.pk, "name": "Roupas", "slug": "roupas"}]


def test_categoria_pelo_nome_reaproveita_a_existente(api):
    """Nome com outra caixa nao pode gerar "roupas-2"."""
    existente = Categoria.objects.create(nome="Roupas", slug="roupas")
    api.post(PRODUTOS, {"name": "A", "categories": [{"name": "ROUPAS"}]}, format="json")
    api.post(PRODUTOS, {"name": "B", "categories": [{"slug": "roupas"}]}, format="json")
    assert list(Categoria.objects.all()) == [existente]
    assert existente.produtos.count() == 2


def test_categoria_pelo_id_continua_valendo(api):
    categoria = Categoria.objects.create(nome="Casa", slug="casa")
    corpo = api.post(PRODUTOS, {"name": "A", "categories": [{"id": categoria.pk}, {"id": 999}]},
                     format="json").json()
    assert [c["id"] for c in corpo["categories"]] == [categoria.pk]
    assert Categoria.objects.count() == 1


def test_tag_pelo_id_nao_apaga_as_tags_do_produto(api):
    """O Woo manda tags como [{"id": 5}]; sem nome, a lista chegava vazia e zerava as tags."""
    tag = Tag.objects.create(nome="Verao")
    corpo = api.post(PRODUTOS, {"name": "A", "tags": [{"id": tag.pk}, {"name": "Nova"}]},
                     format="json").json()
    assert sorted(t["name"] for t in corpo["tags"]) == ["Nova", "Verao"]
    assert Tag.objects.get(nome="Nova").origin == Origin.API


def test_cupom_do_pedido_e_cadastrado_quando_nao_existe(conta):
    """O cupom usado no ERP precisa aparecer no hub, nao so no JSON do pedido."""
    produto = criar_produto("Caneca", sku="CAN-1", price=Decimal("10.00"))
    criar_pedido({
        "line_items": [{"product_id": produto.pk, "quantity": 1, "total": "8.00"}],
        "coupon_lines": [{"code": "PROMO10", "discount": "2.00"}],
    })
    cupom = Cupom.objects.get()
    assert (cupom.name, cupom.value, cupom.discount_type) == (
        "PROMO10", Decimal("2.00"), Cupom.TipoDesconto.VALOR_FIXO)
    # O codigo e interno e aleatorio: o que o ERP mandou identifica pelo nome.
    assert cupom.code != "PROMO10"
    # Rascunho: o valor veio de um pedido, nao de uma regra de desconto revisada.
    assert (cupom.status, cupom.origin) == (Cupom.Status.RASCUNHO, Origin.API)


def test_cupom_existente_nao_e_duplicado_nem_alterado(conta):
    """O cupom e achado pelo nome sem diferenciar maiusculas, como o codigo no Woo."""
    cupom = Cupom.objects.create(name="PROMO10", value=Decimal("10"),
                                 discount_type=Cupom.TipoDesconto.PERCENTUAL)
    criar_pedido({"coupon_lines": [{"code": "promo10", "discount": "3.00"}]})
    cupom.refresh_from_db()
    assert Cupom.objects.count() == 1
    assert (cupom.value, cupom.discount_type) == (Decimal("10"), "percentage")
