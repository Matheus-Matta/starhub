"""Switch "servico no subtotal" (tela do WooCommerce), ligado por padrao.

Sofa R$ 1500 + Montagem R$ 80 somada no item: ligado, o item sai com 1580 no subtotal
e no total, e o subtotal do pedido no ERP bate com o que o cliente pagou.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.core.models import User
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import ItemPedido, Pedido, Servico
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/orders"
TELA = "admin:integracoes_configuracaointegracao_woocommerce"
DADOS_TELA = {"dominio_loja": "https://loja.test", "token_acesso": "ck_1", "segredo_app": "cs_1",
              "acao": "salvar"}


@pytest.fixture
def pedido(conta):
    sofa = criar_produto("Sofa", sku="SOF-1", price=Decimal("1500.00"))
    montagem = Servico.objects.create(nome="Montagem", sku="SERV-MONT", preco=Decimal("80"))
    pedido = Pedido.objects.create(status="processing", total=Decimal("1580.00"))
    item = ItemPedido.objects.create(pedido=pedido, produto=sofa, nome="Sofa", sku="SOF-1",
                                     quantidade=1, preco_unitario=Decimal("1500.00"),
                                     subtotal=Decimal("1580.00"), total=Decimal("1580.00"))
    mesclar_extras(pedido, {"servicos": [
        {"item_id": item.pk, "sku": "SOF-1", "servico": "Montagem", "servico_id": montagem.pk,
         "opcao": "Sim", "preco": "80.00", "somado": True}]})
    pedido.save()
    return pedido, item


def _linha(resposta, item):
    return next(linha for linha in resposta.json()["line_items"] if linha["id"] == item.pk)


def test_sem_configuracao_o_servico_fica_no_subtotal_do_item(api, pedido):
    """O padrao e ligado: o ERP recebia o item sem o servico e o subtotal nao batia."""
    obj, item = pedido
    linha = _linha(api.get(f"{URL}/{obj.pk}"), item)

    assert (linha["subtotal"], linha["total"]) == ("1580.00", "1580.00")


def test_switch_ligado_mantem_o_servico_no_subtotal(api, pedido, conta):
    ConfiguracaoIntegracao.objects.create(account=conta, plataforma="woocommerce",
                                          servico_no_subtotal=True)
    obj, item = pedido

    linha = _linha(api.get(f"{URL}/{obj.pk}"), item)

    assert (linha["subtotal"], linha["total"]) == ("1580.00", "1580.00")
    assert linha["price"] == 1580.0


def test_put_com_o_total_do_get_nao_soma_o_servico_duas_vezes(api, pedido):
    """Ligado, o GET ja manda 1580; somar o servico de novo no PUT gravaria 1660."""
    obj, item = pedido
    linha = _linha(api.get(f"{URL}/{obj.pk}"), item)

    resposta = api.put(f"{URL}/{obj.pk}", {"line_items": [
        {"id": item.pk, "subtotal": linha["subtotal"], "total": linha["total"],
         "meta_data": linha["meta_data"]}]}, format="json")

    assert resposta.status_code == 200, resposta.json()
    item.refresh_from_db()
    assert (item.subtotal, item.total) == (Decimal("1580.00"), Decimal("1580.00"))
    assert _linha(resposta, item)["total"] == "1580.00"


def _operador(client, conta):
    operador = User.objects.create_user("operador", "op@x.test", "senha-forte-123",
                                        account=conta, is_staff=True)
    operador.user_permissions.add(*Permission.objects.filter(
        codename__in=["view_configuracaointegracao", "change_configuracaointegracao"]))
    client.force_login(operador)
    return client


def test_usuario_da_conta_desliga_o_switch_na_tela(client, conta):
    """O switch e da conta: so o superusuario mexia e a loja ficava sem como ajustar."""
    cliente = _operador(client, conta)

    tela = cliente.get(reverse(TELA)).content.decode()
    cliente.post(reverse(TELA), {**DADOS_TELA})  # checkbox desmarcado nao vai no POST

    assert 'name="servico_no_subtotal"' in tela
    assert ConfiguracaoIntegracao.objects.get().servico_no_subtotal is False
