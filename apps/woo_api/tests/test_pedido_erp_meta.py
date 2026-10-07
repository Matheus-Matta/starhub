"""Meta do pedido para o ERP: servico com id/sku do cadastro, agendamento dd-mm-aaaa e
idVendedor da integracao de onde o pedido veio."""

from decimal import Decimal

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Pedido, Servico
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.servicos import vincular
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v3/orders"


def _meta(lista, chave="starhub"):
    return next((m["value"] for m in lista if m["key"] == chave), None)


@pytest.fixture
def pedido(db):
    produto = criar_produto("Poltrona Bergère", sku="POL-BERG-01", price=Decimal("1899.90"))
    pedido = Pedido.objects.create(status="processing", origin="shopify")
    item = pedido.itens.create(produto=produto, nome=produto.nome, sku="POL-BERG-01",
                               quantidade=1, subtotal=Decimal("1899.90"),
                               total=Decimal("1899.90"))
    return pedido, item


def _gravar(pedido, item, agendamento="2026-10-15", servico="Montagem", vinculado=True):
    """Grava como a importacao do Shopify grava (vinculado) ou como um pedido antigo,
    de antes do cadastro de servicos (sem servico_id)."""
    servicos = [{"item_id": item.pk, "sku": item.sku, "servico": servico,
                 "opcao": "Sim", "preco": "120.00"}]
    mesclar_extras(pedido, {
        "entrega": {"agendamento": agendamento, "tipo": "delivery"},
        "servicos": vincular(servicos) if vinculado else servicos,
    })
    pedido.save()


def test_servico_do_item_sai_com_id_nome_sku_e_preco_do_cadastro(api, pedido):
    """Pedido antigo (servico sem servico_id) acha o cadastro pelo nome; o ERP
    reconhece o servico pelo id e pelo SKU, nao pelo texto."""
    pedido, item = pedido
    _gravar(pedido, item, vinculado=False)
    montagem = Servico.objects.create(nome="Montagem", sku="ERP-MONT-10")

    corpo = api.get(f"{URL}/{pedido.pk}").json()

    [linha] = corpo["line_items"]
    assert _meta(linha["meta_data"]) == {"servicos": [{
        "id": montagem.pk, "nome": "Montagem", "sku": "ERP-MONT-10",
        "preco": "120.00", "opcao": "Sim"}]}


def test_servico_sem_cadastro_e_criado_ao_gravar_e_vinculado(api, pedido):
    pedido, item = pedido
    corpo = api.put(f"{URL}/{pedido.pk}", {"line_items": [{"id": item.pk, "meta_data": [
        {"key": "starhub", "value": {"servicos": [
            {"nome": "Impermeabilização da poltrona", "opcao": "Sim", "preco": "499,99"}]}}]}]},
        format="json").json()

    novo = Servico.objects.get()
    assert novo.sku == "SERV-IMPERMEABILIZACAO-DA-POLTRONA"
    assert _meta(corpo["line_items"][0]["meta_data"])["servicos"][0]["id"] == novo.pk


@pytest.mark.parametrize("guardado", ["2026-10-15", "15/10/2026", "15-10-2026",
                                      "2026-10-15T14:00:00-03:00"])
def test_agendamento_sai_no_formato_brasileiro(api, pedido, guardado):
    """Cada origem manda a data de um jeito; o ERP le sempre dd-mm-aaaa."""
    pedido, item = pedido
    _gravar(pedido, item, agendamento=guardado)

    corpo = api.get(f"{URL}/{pedido.pk}").json()

    assert _meta(corpo["meta_data"])["entrega"]["agendamento"] == "15-10-2026"


def test_agendamento_que_nao_e_data_sai_como_veio(api, pedido):
    """Texto livre ("a combinar") nao pode virar data inventada nem sumir."""
    pedido, item = pedido
    _gravar(pedido, item, agendamento="a combinar")

    corpo = api.get(f"{URL}/{pedido.pk}").json()

    assert _meta(corpo["meta_data"])["entrega"]["agendamento"] == "a combinar"


def test_id_vendedor_sai_inteiro_com_o_numero_da_integracao_de_origem(api, pedido, conta):
    pedido, item = pedido
    _gravar(pedido, item)
    ConfiguracaoIntegracao.objects.create(account=conta, plataforma="shopify", id_vendedor=12)

    corpo = api.get(f"{URL}/{pedido.pk}").json()

    assert _meta(corpo["meta_data"])["idVendedor"] == 12


def test_sem_id_vendedor_configurado_o_campo_nao_sai(api, pedido, conta):
    """Origem sem numero configurado: melhor ausente do que um 0 que o ERP aceitaria."""
    pedido, item = pedido
    _gravar(pedido, item)
    ConfiguracaoIntegracao.objects.create(account=conta, plataforma="shopify")

    corpo = api.get(f"{URL}/{pedido.pk}").json()

    assert "idVendedor" not in _meta(corpo["meta_data"])


def test_erp_devolve_o_que_recebeu_sem_duplicar_nem_trocar_servico(api, pedido):
    pedido, item = pedido
    _gravar(pedido, item)
    corpo = api.get(f"{URL}/{pedido.pk}").json()

    depois = api.put(f"{URL}/{pedido.pk}", {"meta_data": corpo["meta_data"],
                                            "line_items": corpo["line_items"]},
                     format="json").json()

    assert _meta(depois["line_items"][0]["meta_data"]) == _meta(
        corpo["line_items"][0]["meta_data"])
    assert Servico.objects.count() == 1
    assert _meta(depois["meta_data"])["entrega"]["agendamento"] == "15-10-2026"


def test_id_vendedor_devolvido_pelo_erp_nao_e_gravado(api, pedido, conta):
    """Gravado, o numero antigo seguiria saindo depois de trocarem o da integracao."""
    pedido, item = pedido
    _gravar(pedido, item)
    config = ConfiguracaoIntegracao.objects.create(account=conta, plataforma="shopify",
                                                   id_vendedor=12)
    corpo = api.get(f"{URL}/{pedido.pk}").json()
    api.put(f"{URL}/{pedido.pk}", {"meta_data": corpo["meta_data"]}, format="json")
    config.id_vendedor = None
    config.save()

    assert "idVendedor" not in _meta(api.get(f"{URL}/{pedido.pk}").json()["meta_data"])
