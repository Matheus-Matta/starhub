"""Cada log do auditlog diz de onde veio a alteracao (apps/core/origem.py): admin,
woo_api (com a chave ou o usuario do JWT) ou sistema; e a lista de logs mostra."""

from auditlog.models import LogEntry
from rest_framework.test import APIClient

from apps.core.origem import origem
from apps.loja.models import Produto
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v1/products"


def _log_de(produto, acao=LogEntry.Action.CREATE):
    return LogEntry.objects.get_for_object(produto).filter(action=acao).first()


def test_alteracao_pela_chave_da_api_fica_woo_api_com_a_chave(api):
    assert api.post(URL, {"name": "Caneca", "sku": "CAN-1"}, format="json").status_code == 201
    log = _log_de(Produto.objects.get())
    assert log.additional_data["origem"] == "woo_api"
    assert log.additional_data["via"].startswith("ERP (...")
    assert log.actor is None


def test_alteracao_pelo_jwt_fica_woo_api_com_o_usuario(usuario_erp):
    cliente = APIClient()
    token = cliente.post("/wp-json/jwt-auth/v1/token",
                         {"username": "erp", "password": "senha-do-erp-123"}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token.json()['token']}")
    assert cliente.post(URL, {"name": "Caneca", "sku": "CAN-2"}, format="json").status_code == 201
    log = _log_de(Produto.objects.get())
    assert log.additional_data["origem"] == "woo_api" and log.actor == usuario_erp


def test_alteracao_no_admin_fica_admin_com_o_usuario(admin_logado, conta):
    produto = criar_produto("Camiseta", sku="CAM-1")
    dados = {"nome": "Camiseta azul", "slug": produto.slug, "tipo": "simple",
             "status": "publish", "visibilidade": "visible", "atributos": "[]",
             "metadados": "[]", "ordem_menu": "0", "id_pai": "0", "_continue": "1",
             "variantes-TOTAL_FORMS": "1", "variantes-INITIAL_FORMS": "1",
             "variantes-0-id": produto.variante_padrao.pk, "variantes-0-produto": produto.pk,
             "variantes-0-sku": "CAM-1", "variantes-0-imagens": "[]",
             "variantes-0-dimensions": "{}", "variantes-0-weight_unit": "kg",
             "variantes-0-inventory_policy": "deny", "variantes-0-stock_status": "instock",
             "variantes-0-tax_status": "taxable", "variantes-0-inventory_quantity": "0",
             "variantes-0-posicao": "0",
             "componentes-TOTAL_FORMS": "0", "componentes-INITIAL_FORMS": "0"}
    resposta = admin_logado.post(f"/admin/loja/produto/{produto.pk}/change/", dados)
    assert resposta.status_code == 302
    log = _log_de(produto, LogEntry.Action.UPDATE)
    assert log.additional_data["origem"] == "admin" and log.actor.username == "admin"
    # Criado fora de requisicao (servico, comando): sistema.
    assert _log_de(produto).additional_data["origem"] == "sistema"


def test_integracao_marca_a_propria_origem(conta):
    with origem("shopify", via="Loja Shopify"):
        produto = criar_produto("Tenis", sku="TEN-1")
    assert _log_de(produto).additional_data == {
        "account_id": str(conta.pk), "origem": "shopify", "via": "Loja Shopify"
    }


def test_lista_de_logs_mostra_e_filtra_a_origem(api, admin_logado):
    api.post(URL, {"name": "Caneca", "sku": "CAN-1"}, format="json")
    criar_produto("Camiseta", sku="CAM-1")
    lista = admin_logado.get("/admin/auditlog/logentry/?origem=woo_api")
    logs = list(lista.context["cl"].result_list)
    assert logs and {log.additional_data["origem"] for log in logs} == {"woo_api"}
    assert '<span class="badge badge-primary">woo_api</span> ERP (...' in lista.content.decode()
    sistema = admin_logado.get("/admin/auditlog/logentry/?origem=sistema").context["cl"]
    assert "Camiseta" in {log.object_repr for log in sistema.result_list}
