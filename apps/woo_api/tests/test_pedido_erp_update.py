"""Update de pedido (PUT/PATCH/lote, v1 e v3) aceita os servicos como o GET mostra:
pelo id ou SKU do cadastro, e sem preco usa a regra do produto."""

from decimal import Decimal

import pytest

from apps.loja.models import Pedido, RegraServico, Servico
from apps.loja.services.extras_pedido import extras
from apps.loja.services.variantes import criar_produto

V3 = "/wp-json/wc/v3/orders"
V1 = "/wp-json/wc/v1/orders"


@pytest.fixture
def cenario(db):
    produto = criar_produto("Sofa compacto", sku="SOF-1", price=Decimal("1500.00"))
    pedido = Pedido.objects.create(status="processing", origin="shopify")
    item = pedido.itens.create(produto=produto, nome=produto.nome, sku="SOF-1", quantidade=1,
                               total=Decimal("1500.00"))
    montagem = Servico.objects.create(nome="Montagem", sku="ERP-MONT", preco=Decimal("120.00"))
    return pedido, item, montagem


def _put(api, url, pedido, item, servicos):
    return api.put(f"{url}/{pedido.pk}", {"line_items": [{"id": item.pk, "meta_data": [
        {"key": "starhub", "value": {"servicos": servicos}}]}]}, format="json")


def _saida(resposta):
    meta = resposta.json()["line_items"][0]["meta_data"]
    return next(m["value"]["servicos"] for m in meta if m["key"] == "starhub")


@pytest.mark.parametrize("url", [V3, V1])
def test_servico_pelo_id_do_cadastro_sem_nome(api, cenario, url):
    """O ERP devolve so o id que recebeu no GET: antes o servico ficava sem nome."""
    pedido, item, montagem = cenario

    resposta = _put(api, url, pedido, item, [{"id": montagem.pk, "opcao": "Sim",
                                              "preco": "100.00"}])

    assert resposta.status_code == 200, resposta.json()
    assert _saida(resposta) == [{"id": montagem.pk, "nome": "Montagem", "sku": "ERP-MONT",
                                 "preco": "100.00", "opcao": "Sim"}]
    pedido.refresh_from_db()
    [guardado] = extras(pedido)["servicos"]
    assert (guardado["servico"], guardado["servico_id"]) == ("Montagem", montagem.pk)


def test_servico_pelo_sku_do_cadastro(api, cenario):
    pedido, item, montagem = cenario

    resposta = _put(api, V3, pedido, item, [{"sku": "ERP-MONT", "opcao": "Sim",
                                             "preco": "100.00"}])

    assert _saida(resposta)[0]["id"] == montagem.pk


@pytest.mark.parametrize("referencia", [{"id": 999999}, {"sku": "NAO-EXISTE"}])
def test_id_ou_sku_que_nao_existe_e_recusado_dizendo_o_que_fazer(api, cenario, referencia):
    """Criar servico pelo id inventado gravaria lixo; o ERP precisa corrigir o envio."""
    pedido, item, _ = cenario

    resposta = _put(api, V3, pedido, item, [{**referencia, "opcao": "Sim", "preco": "10"}])

    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["code"] == "rest_invalid_param"
    # Como no Woo: o detalhe do campo vai em data.params, a message so diz qual campo.
    assert "Loja > Servicos" in corpo["data"]["params"]["line_items"]
    assert not Pedido.objects.get(pk=pedido.pk).itens.exclude(pk=item.pk).exists()


def test_servico_sem_preco_usa_a_regra_do_produto(api, cenario):
    pedido, item, montagem = cenario
    regra = RegraServico.objects.create(servico=montagem, ordem=10, preco=Decimal("90.00"),
                                        tipo=RegraServico.Tipo.PRODUTO)
    regra.produtos.set([item.produto])

    resposta = _put(api, V3, pedido, item, [{"id": montagem.pk, "opcao": "Sim"}])

    assert _saida(resposta)[0]["preco"] == "90.00"


def test_servico_sem_preco_e_sem_regra_usa_o_preco_padrao(api, cenario):
    pedido, item, montagem = cenario

    resposta = _put(api, V3, pedido, item, [{"nome": "Montagem", "opcao": "Sim"}])

    assert _saida(resposta)[0]["preco"] == "120.00"


def test_lote_de_update_aceita_o_mesmo_formato(api, cenario):
    pedido, item, montagem = cenario

    resposta = api.post(f"{V3}/batch", {"update": [{"id": pedido.pk, "line_items": [
        {"id": item.pk, "meta_data": [{"key": "starhub", "value": {"servicos": [
            {"id": montagem.pk, "opcao": "Sim"}]}}]}]}]}, format="json")

    assert resposta.status_code == 200
    [atualizado] = resposta.json()["update"]
    servicos = next(m["value"]["servicos"] for m in atualizado["line_items"][0]["meta_data"]
                    if m["key"] == "starhub")
    assert servicos[0]["nome"] == "Montagem" and servicos[0]["preco"] == "120.00"


def test_agendamento_enviado_em_dd_mm_aaaa_volta_igual(api, cenario):
    pedido, _, _ = cenario

    resposta = api.put(f"{V3}/{pedido.pk}", {"meta_data": [{"key": "starhub", "value": {
        "entrega": {"agendamento": "20-10-2026", "tipo": "delivery"}}}]}, format="json")

    starhub = next(m["value"] for m in resposta.json()["meta_data"] if m["key"] == "starhub")
    assert starhub["entrega"]["agendamento"] == "20-10-2026"
