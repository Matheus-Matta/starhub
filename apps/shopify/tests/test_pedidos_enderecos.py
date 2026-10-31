from apps.integracoes.models import ConfiguracaoIntegracao
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.contexto import coletando_avisos, usando_configuracao
from apps.shopify.pedidos_documento import completar_documento
from apps.shopify.pedidos_enderecos import documento, endereco_woo


def test_caractere_invisivel_do_checkout_nao_impede_separar_numero_e_bairro():
    """O checkout do Shopify colou U+2060 antes do numero e do bairro (pedido #3243):
    o numero nao era achado e o bairro ia para o ERP com o caractere invisivel."""
    dados = {"email": "a@b.test", "billing_address": {
        "address1": "Avenida Abdias Jose dos Santos, ⁠5707",
        "address2": "Apartamento 601, ⁠Rio do Ouro", "city": "Sao Goncalo",
    }}
    woo = endereco_woo(dados, "billing")
    assert (woo["address_1"], woo["number"]) == ("Avenida Abdias Jose dos Santos", "5707")
    assert woo["neighborhood"] == "Rio do Ouro"
    assert woo["address_2"] == "Apartamento 601, Rio do Ouro"


CPF_CHECKOUT = {"purpose": "TAX", "countryCode": "BR", "title": "CPF/CNPJ",
                "value": "390.533.447-05"}
LOJA = ConfiguracaoIntegracao(dominio_loja="totvsrj-maxxxmoveis-dc.myshopify.com",
                              versao_api="2026-07")


def test_cpf_do_checkout_brasileiro_vai_para_o_billing():
    """O Shopify guarda o CPF em localizationExtensions, nao em note_attributes: sem
    le-lo o pedido chegava ao ERP sem CPF e o cadastro do cliente falhava."""
    dados = {"localization_extensions": [CPF_CHECKOUT],
             "billing_address": {"address1": "Rua A, 10", "city": "Recife"}}
    woo = endereco_woo(dados, "billing")
    assert (woo["cpf"], woo["persontype"]) == ("39053344705", "1")


def test_documento_e_buscado_na_api_2024_01_com_a_consulta_do_fluxo_antigo(monkeypatch):
    """localizationExtensions e da API antiga; na versao da configuracao (2026-07)
    a consulta poderia nao existir."""
    chamadas = []

    def graphql(self, query, variables=None):
        chamadas.append((self.endpoint, variables, "localizationExtensions" in query))
        return {"order": {"localizationExtensions": {"nodes": [CPF_CHECKOUT]}}}

    monkeypatch.setattr(ShopifyClient, "graphql", graphql)
    with usando_configuracao(LOJA):
        dados = completar_documento({"admin_graphql_api_id": "gid://shopify/Order/1"})
    assert chamadas == [(
        "https://totvsrj-maxxxmoveis-dc.myshopify.com/admin/api/2024-01/graphql.json",
        {"id": "gid://shopify/Order/1"}, True)]
    assert documento(dados) == "39053344705"


def test_falha_ao_ler_o_cpf_avisa_e_nao_derruba_o_pedido(monkeypatch):
    def graphql(self, query, variables=None):
        raise ShopifyErro("Access denied for localizationExtensions")

    monkeypatch.setattr(ShopifyClient, "graphql", graphql)
    with coletando_avisos() as avisos, usando_configuracao(LOJA):
        dados = completar_documento({"admin_graphql_api_id": "gid://shopify/Order/1"})
    assert documento(dados) == ""
    assert "CPF/CNPJ do checkout nao lido" in str(avisos)
