"""Base do id do pedido na API Woo: id da API = id do hub + base (ex.: 1 -> 13001).

O ERP legado importa pedidos em sequencia pelo id ha anos; o id do hub, que recomeca
do 1, colidiria com os pedidos antigos dele.
"""

import pytest
from django.urls import reverse

from apps.core.tenant.context import tenant_context
from apps.loja.models import Pedido
from apps.woo_api.models import ConfiguracaoFdc
from apps.woo_api.recursos.pedidos_saida import pedido_para_woo
from apps.woo_api.tests.conftest import criar_pedido

BASE = 13000
VERSOES = ["v1", "v3"]
LISTA = "admin:woo_api_configuracaofdc_changelist"


@pytest.fixture
def loja(conta):
    return ConfiguracaoFdc.objects.create(account=conta, base_id_pedido=BASE)


def _tela(conta):
    return reverse("admin:woo_api_configuracaofdc_change",
                   args=[ConfiguracaoFdc.objects.get(account=conta).pk])


def _pedido():
    criar_pedido()
    return Pedido.objects.latest("pk")


@pytest.mark.parametrize("versao", VERSOES)
def test_lista_e_detalhe_devolvem_o_id_somado_a_base(api, loja, versao):
    """Sem a soma, o ERP importava por cima dos pedidos antigos de mesmo numero."""
    pedido = _pedido()
    esperado = pedido.pk + BASE

    lista = api.get(f"/wp-json/wc/{versao}/orders").json()
    detalhe = api.get(f"/wp-json/wc/{versao}/orders/{esperado}")

    assert [item["id"] for item in lista] == [esperado]
    assert detalhe.status_code == 200
    assert detalhe.json()["id"] == esperado and detalhe.json()["number"] == str(esperado)


@pytest.mark.parametrize("versao", VERSOES)
def test_id_abaixo_da_base_nao_acha_pedido_do_hub(api, loja, versao):
    """O 5 do ERP e um pedido antigo dele: nao pode cair no pedido 5 do hub."""
    pedido = _pedido()

    resposta = api.put(f"/wp-json/wc/{versao}/orders/{pedido.pk}",
                       {"status": "completed"}, format="json")

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "woocommerce_rest_shop_order_invalid_id"
    pedido.refresh_from_db()
    assert pedido.status != "completed"


def test_a_propria_base_nao_e_pedido(api, loja):
    assert api.get(f"/wp-json/wc/v3/orders/{BASE}").status_code == 404


@pytest.mark.parametrize("versao", VERSOES)
def test_put_pelo_id_da_api_grava_no_pedido_certo(api, loja, versao):
    pedido = _pedido()

    resposta = api.put(f"/wp-json/wc/{versao}/orders/{pedido.pk + BASE}",
                       {"status": "completed"}, format="json")

    assert resposta.status_code == 200 and resposta.json()["id"] == pedido.pk + BASE
    pedido.refresh_from_db()
    assert pedido.status == "completed"


def test_lote_usa_o_id_da_api_nos_dois_sentidos(api, loja):
    pedido = _pedido()

    resposta = api.post("/wp-json/wc/v3/orders/batch", {"update": [
        {"id": pedido.pk + BASE, "status": "completed"},
        {"id": pedido.pk, "status": "cancelled"},
    ]}, format="json").json()["update"]

    assert resposta[0]["id"] == pedido.pk + BASE and resposta[0]["status"] == "completed"
    assert resposta[1]["id"] == pedido.pk and "error" in resposta[1]
    pedido.refresh_from_db()
    assert pedido.status == "completed"


def test_include_e_exclude_filtram_pelo_id_da_api(api, loja):
    primeiro, segundo = _pedido(), _pedido()
    url = "/wp-json/wc/v3/orders"

    incluidos = api.get(url, {"include": f"{primeiro.pk + BASE},{segundo.pk}"}).json()
    excluidos = api.get(url, {"exclude": primeiro.pk + BASE}).json()

    assert [p["id"] for p in incluidos] == [primeiro.pk + BASE]
    assert [p["id"] for p in excluidos] == [segundo.pk + BASE]


def test_sem_configuracao_o_id_e_o_do_hub(api):
    pedido = _pedido()

    assert api.get(f"/wp-json/wc/v3/orders/{pedido.pk}").json()["id"] == pedido.pk


def test_desligar_a_integracao_nao_renumera_os_pedidos(api, loja):
    """Inativa, a base sumia e o ERP via os mesmos pedidos com outro id: duplicava tudo."""
    pedido = _pedido()
    ConfiguracaoFdc.objects.filter(pk=loja.pk).update(active=False)

    assert api.get(f"/wp-json/wc/v3/orders/{pedido.pk + BASE}").json()["id"] == pedido.pk + BASE


def test_base_de_uma_conta_nao_vale_na_outra(loja, outra_conta):
    with tenant_context(outra_conta):
        pedido = _pedido()

        assert pedido_para_woo(pedido)["id"] == pedido.pk


def test_tela_do_json_mostra_o_id_que_o_erp_recebe(admin_logado, loja):
    """A rota da tela e copiada para conferir na API: com o id do hub ela dava 404."""
    pedido = _pedido()

    html = admin_logado.get(reverse("admin:loja_pedido_json", args=[pedido.pk])).content.decode()

    assert f"GET /wc/v3/orders/{pedido.pk + BASE}" in html


def test_menu_fdc_abre_a_configuracao_da_conta_criada_na_hora(admin_logado, conta):
    """Sem configuracao a conta nao tinha onde por a base: a tela cria a dela."""
    resposta = admin_logado.get(reverse(LISTA))

    assert resposta.status_code == 302 and resposta.url == _tela(conta)


def test_superusuario_grava_a_base_na_tela(admin_logado, conta):
    admin_logado.get(reverse(LISTA))
    admin_logado.post(_tela(conta), {"base_id_pedido": str(BASE)})

    assert ConfiguracaoFdc.objects.get().base_id_pedido == BASE


def test_salvar_com_a_base_vazia_nao_renumera_os_pedidos(admin_logado, conta, loja):
    """Campo apagado sem querer zeraria a base e mudaria o id de todos os pedidos."""
    admin_logado.post(_tela(conta), {"base_id_pedido": ""})

    assert ConfiguracaoFdc.objects.get().base_id_pedido == BASE


def test_usuario_da_conta_ve_e_muda_a_base(client, conta, loja):
    """A base e da conta (o ERP dela): so o superusuario mudava e a loja dependia dele."""
    from django.contrib.auth.models import Permission

    from apps.core.models import User

    operador = User.objects.create_user("operador", "op@x.test", "senha-forte-123",
                                        account=conta, is_staff=True)
    operador.user_permissions.add(*Permission.objects.filter(
        codename__in=["view_configuracaofdc", "change_configuracaofdc"]))
    client.force_login(operador)

    tela = client.get(_tela(conta)).content.decode()
    client.post(_tela(conta), {"base_id_pedido": "20000"})

    assert 'name="base_id_pedido"' in tela
    assert ConfiguracaoFdc.objects.get().base_id_pedido == 20000
