"""`name` do ERP na v3 vai para o produto ou para a variante que o SKU/id acha.

Antes era ignorado: so preco, promocao e estoque mudavam.
"""

from decimal import Decimal

import pytest

from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/products"


@pytest.fixture
def camiseta(conta):
    produto = criar_produto("Camiseta Gola", sku="CAM-P", price=Decimal("50.00"))
    produto.tipo = Produto.Tipo.VARIAVEL
    produto.save()
    VarianteProduto.objects.create(produto=produto, titulo="M", sku="CAM-M",
                                   price=Decimal("60.00"), posicao=1)
    return produto


def _id_variacao(api):
    return api.get(URL, {"sku": "CAM-M"}).json()[0]["id"]


def _titulos():
    return dict(VarianteProduto.objects.values_list("sku", "titulo"))


@pytest.mark.parametrize(("name", "titulo"), [
    ("Camiseta Gola - Azul Royal", "Azul Royal"),
    ("CAMISETA GOLA | G", "G"),
    ("Gola V Listrada", "Gola V Listrada"),
])
def test_nome_da_variacao_vira_o_titulo_dela(api, camiseta, name, titulo):
    resposta = api.put(f"{URL}/{camiseta.pk}/variations/{_id_variacao(api)}",
                       {"name": name, "regular_price": "70.00"}, format="json")

    assert resposta.status_code == 200
    assert _titulos() == {"CAM-P": "Default", "CAM-M": titulo} or \
        _titulos()["CAM-M"] == titulo
    assert resposta.json()["name"] == f"Camiseta Gola - {titulo}"
    assert Produto.objects.get().nome == "Camiseta Gola"


def test_so_o_nome_do_produto_na_variacao_mantem_o_titulo(api, camiseta):
    """O ERP manda "SOFA X-" (o nome do pai com um traco): nada sobra para a variante."""
    api.put(f"{URL}/{camiseta.pk}/variations/{_id_variacao(api)}",
            {"name": "Camiseta Gola-", "stock_quantity": "3"}, format="json")

    assert _titulos()["CAM-M"] == "M"
    assert Produto.objects.get().nome == "Camiseta Gola"


def test_sku_da_variacao_no_post_tambem_poe_o_titulo(api, camiseta):
    api.post(URL, {"id": "0", "sku": "CAM-M", "name": "Camiseta Gola - Verde"}, format="json")
    assert _titulos()["CAM-M"] == "Verde"


def test_produto_simples_pelo_sku_recebe_o_nome(api, conta):
    produto = criar_produto("Mesa", sku="MESA-1", price=Decimal("10"))

    resposta = api.post(URL, {"id": "0", "sku": "MESA-1", "name": "Mesa de Jantar 6 Lugares"},
                        format="json")

    assert resposta.json()["id"] == produto.pk
    assert Produto.objects.get().nome == "Mesa de Jantar 6 Lugares"


def test_put_pelo_id_do_produto_muda_o_nome_dele(api, conta):
    produto = criar_produto("Mesa", sku="MESA-1", price=Decimal("10"))

    api.put(f"{URL}/{produto.pk}", {"name": "Mesa Redonda", "regular_price": "12.00"},
            format="json")

    produto.refresh_from_db()
    assert produto.nome == "Mesa Redonda"
    assert VarianteProduto.objects.get(sku="MESA-1").price == Decimal("12.00")


def test_nome_vazio_nao_apaga_nada(api, camiseta):
    api.put(f"{URL}/{camiseta.pk}", {"name": "  ", "sku": "CAM-M"}, format="json")
    api.put(f"{URL}/{camiseta.pk}", {"name": ""}, format="json")

    assert Produto.objects.get().nome == "Camiseta Gola"
    assert _titulos()["CAM-M"] == "M"
