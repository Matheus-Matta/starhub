"""O servico que o hub somou no item sai dele no GET: o ERP soma o servico (EPOFW).

Sofa R$ 1500 + Montagem R$ 80 (linha propria no Shopify, somada no item): o hub guarda
o item com 1580; o ERP recebia 1580 + o servico 80 e via total diferente do pedido.
"""

from decimal import Decimal

import pytest

from apps.loja.models import ItemPedido, Pedido, Servico
from apps.loja.services.extras_pedido import extras, mesclar_extras
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/orders"


@pytest.fixture
def pedido(conta):
    sofa = criar_produto("Sofa", sku="SOF-1", price=Decimal("1500.00"))
    montagem = Servico.objects.create(nome="Montagem", sku="SERV-MONT", preco=Decimal("80"))
    pedido = Pedido.objects.create(status="processing", total=Decimal("1650.00"))
    com = ItemPedido.objects.create(pedido=pedido, produto=sofa, nome="Sofa", sku="SOF-1",
                                    quantidade=2, preco_unitario=Decimal("750.00"),
                                    subtotal=Decimal("1580.00"), total=Decimal("1580.00"))
    sem = ItemPedido.objects.create(pedido=pedido, nome="Almofada", sku="ALM-1",
                                    quantidade=1, subtotal=Decimal("70.00"),
                                    total=Decimal("70.00"))
    mesclar_extras(pedido, {"servicos": [
        {"item_id": com.pk, "sku": "SOF-1", "servico": "Montagem", "servico_id": montagem.pk,
         "opcao": "Sim", "preco": "80.00", "somado": True},
        # Servico so informado (propriedade do item): nunca foi somado, nada sai.
        {"item_id": sem.pk, "sku": "ALM-1", "servico": "Garantia", "opcao": "Sim",
         "preco": "15.00"}]})
    pedido.save()
    return pedido, com, sem


def _linhas(resposta):
    return {linha["id"]: linha for linha in resposta.json()["line_items"]}


def test_get_tira_do_item_so_o_servico_que_o_hub_somou(api, pedido):
    obj, com, sem = pedido
    resposta = api.get(f"{URL}/{obj.pk}")

    linhas = _linhas(resposta)
    assert (linhas[com.pk]["subtotal"], linhas[com.pk]["total"]) == ("1500.00", "1500.00")
    assert linhas[com.pk]["price"] == 750.0
    assert linhas[sem.pk]["total"] == "70.00"
    assert resposta.json()["total"] == "1650.00", "o cliente pagou o servico"


def test_put_com_o_total_do_get_nao_tira_o_servico_do_pedido(api, pedido):
    """Sem somar de volta, cada PUT do ERP baixava o item para 1500 e o pedido para 1570."""
    obj, com, _sem = pedido
    linha = _linhas(api.get(f"{URL}/{obj.pk}"))[com.pk]

    resposta = api.put(f"{URL}/{obj.pk}", {"line_items": [
        {"id": com.pk, "subtotal": linha["subtotal"], "total": linha["total"],
         "meta_data": linha["meta_data"]}]}, format="json")

    assert resposta.status_code == 200, resposta.json()
    com.refresh_from_db()
    assert (com.subtotal, com.total) == (Decimal("1580.00"), Decimal("1580.00"))
    assert _linhas(resposta)[com.pk]["total"] == "1500.00"
    servico = next(s for s in extras(com.pedido)["servicos"] if s["item_id"] == com.pk)
    assert servico["somado"] is True, "sem a marca o proximo GET contaria duas vezes"


def test_envio_a_loja_woocommerce_continua_com_o_servico_no_item(pedido):
    from apps.woocommerce.envio.pedidos_legado import corpo

    obj, com, _sem = pedido
    padrao = {linha["name"]: linha["total"] for linha in corpo(obj, legado=False)["line_items"]}
    legado = {linha["name"]: linha["total"] for linha in corpo(obj, legado=True)["line_items"]}
    assert (padrao["Sofa"], legado["Sofa"]) == ("1580.00", "1500.00")
