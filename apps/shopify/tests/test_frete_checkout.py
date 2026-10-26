"""Frete do StarHub no checkout da Shopify: cotacao, rota assinada e o pedido."""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.logistica import geo, geo_rede
from apps.logistica.models import FaixaCep, TabelaFrete
from apps.loja.models import Pedido
from apps.shopify.frete import ORCAMENTO_SEGUNDOS, dias_uteis, opcoes_de_frete
from apps.shopify.pedidos_entrega import gravar_frete
from apps.shopify.tests.test_webhooks import _assinatura, _configuracao

pytestmark = pytest.mark.django_db
CHECKOUT = {"rate": {"origin": {"country": "BR", "postal_code": "01001000"},
                     "destination": {"country": "BR", "postal_code": "24400-000"},
                     "items": [{"name": "Camiseta", "quantity": 2, "grams": 500,
                                "price": 8990}]}}


def _faixa(nome="Tabela RJ", valor="25.00", checkout=True, **extra):
    tabela = TabelaFrete.objects.create(nome=nome, tipo="faixa_cep", prazo_dias=3,
                                        no_checkout=checkout, **extra)
    FaixaCep.objects.create(tabela=tabela, cep_inicial="20000000", cep_final="28999999",
                            valor=Decimal(valor))
    return tabela


def test_cada_tabela_do_checkout_vira_uma_opcao_em_centavos():
    tabela = _faixa(valor="38.91")
    distancia = TabelaFrete.objects.create(
        nome="Entrega propria", tipo="distancia", cep_origem="01001000",
        preco_por_km=Decimal("0.10"), prazo_dias=1, no_checkout=True)
    with patch.object(geo, "km_entre_ceps", lambda *args: (Decimal("50.0"), True)):
        opcoes = opcoes_de_frete(CHECKOUT)
    assert [o["service_code"] for o in opcoes] == [f"HUB_{distancia.pk}", f"HUB_{tabela.pk}"]
    rj = opcoes[1]
    assert (rj["service_name"], rj["total_price"], rj["currency"]) == ("Tabela RJ", "3891", "BRL")
    assert rj["description"] == "Entrega em 3 dias uteis"
    assert rj["min_delivery_date"].endswith("18:00:00 -0300")


def test_so_entram_as_ativas_marcadas_e_que_atendem_o_cep():
    """Tabela fora do checkout, desativada ou sem faixa para o CEP nao aparece."""
    _faixa("Fora do checkout", checkout=False)
    _faixa("Desativada", active=False)
    so_sp = TabelaFrete.objects.create(nome="So SP", tipo="faixa_cep", no_checkout=True)
    FaixaCep.objects.create(tabela=so_sp, cep_inicial="01000000", cep_final="09999999",
                            valor=Decimal("10"))
    assert opcoes_de_frete(CHECKOUT) == []


def test_depois_do_orcamento_de_tempo_as_tabelas_que_faltam_ficam_de_fora():
    """A Shopify desiste em 3 s: melhor mostrar a que ja saiu do que nenhuma."""
    _faixa("A"), _faixa("B")
    relogio = iter([0, 0, ORCAMENTO_SEGUNDOS + 1])
    assert [o["service_name"] for o in opcoes_de_frete(CHECKOUT, lambda: next(relogio))] == ["A"]


def test_prazo_pula_o_fim_de_semana():
    sexta = datetime(2026, 10, 2, 9)
    assert dias_uteis(sexta, 1).date().isoformat() == "2026-10-05"  # segunda
    assert dias_uteis(sexta, 0) == sexta


def _post(client, configuracao, corpo, assinatura=None):
    bruto = json.dumps(corpo).encode()
    return client.post(f"/integracoes/shopify/frete/{configuracao.uuid}/", data=bruto,
                       content_type="application/json",
                       HTTP_X_SHOPIFY_HMAC_SHA256=assinatura or _assinatura(bruto))


def test_rota_assinada_responde_as_opcoes_no_formato_da_shopify(client, conta):
    configuracao = _configuracao(conta)
    tabela = _faixa()
    resposta = _post(client, configuracao, CHECKOUT)
    assert resposta.status_code == 200
    assert resposta.json()["rates"][0]["service_code"] == f"HUB_{tabela.pk}"


def test_configuracao_pode_ocultar_o_prazo_no_checkout(client, conta):
    """Ocultar prazo mantem a descricao obrigatoria para a Shopify aceitar a tarifa."""
    configuracao = _configuracao(conta)
    configuracao.exibir_prazo_frete = False
    configuracao.save(update_fields=["exibir_prazo_frete"])
    _faixa()

    opcao = _post(client, configuracao, CHECKOUT).json()["rates"][0]

    assert opcao["description"] == "Frete calculado pelo StarHub"
    assert {"min_delivery_date", "max_delivery_date"}.isdisjoint(opcao)
    assert (opcao["service_name"], opcao["total_price"]) == ("Tabela RJ", "2500")


def test_rota_aceita_a_cotacao_sem_hmac_de_webhook(client, conta):
    """CarrierService nao assina a cotacao como webhook; exigir HMAC esconde o frete."""
    configuracao = _configuracao(conta)
    tabela = _faixa()
    resposta = client.post(
        f"/integracoes/shopify/frete/{configuracao.uuid}/",
        data=json.dumps(CHECKOUT).encode(),
        content_type="application/json",
    )
    assert resposta.status_code == 200
    assert resposta.json()["rates"][0]["service_code"] == f"HUB_{tabela.pk}"


def test_rota_de_loja_desconhecida_e_recusada(client, conta):
    """O UUID impede misturar a cotacao com uma configuracao que nao existe."""
    _configuracao(conta)
    resposta = client.post("/integracoes/shopify/frete/00000000-0000-0000-0000-000000000000/",
                           data=b"{}", content_type="application/json")
    assert resposta.status_code == 404


def test_frete_escolhido_chega_no_pedido_com_o_codigo_da_tabela():
    """O shipping_lines do orders/create grava qual tabela do hub o cliente escolheu."""
    pedido = Pedido()
    gravar_frete(pedido, {"shipping_lines": [
        {"code": "HUB_3", "title": "Tabela RJ", "price": "38.91", "source": "StarHub Frete"}]})
    linha = pedido.linhas_frete[0]
    assert (linha["method_id"], linha["method_title"], linha["total"]) == (
        "HUB_3", "Tabela RJ", "38.91")


def test_cidade_e_uf_do_checkout_vao_para_a_cotacao():
    TabelaFrete.objects.create(nome="Km", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("1"), no_checkout=True)
    recebidos = []

    def km(origem, destino, timeout, cidade, uf):
        recebidos.append((destino, cidade, uf))
        return Decimal("10.0"), True

    corpo = {"rate": {"destination": {"postal_code": "24400000", "city": "Sao Goncalo",
                                      "province": "RJ"}}}
    with patch.object(geo, "km_entre_ceps", km):
        assert opcoes_de_frete(corpo)[0]["total_price"] == "1000"
    assert recebidos == [("24400000", "Sao Goncalo", "RJ")]


def test_api_que_demora_mais_de_um_segundo_ainda_da_frete():
    """Pedido #3186: CEP novo, API lenta no primeiro acesso (BrasilAPI 2,5 s, Nominatim
    1 s medidos). Com 0,8 s por chamada o CEP nao era localizado, a lista ia vazia e a
    Shopify usava o backup rate. Ela espera ate 10 s (loja com menos de 1500 RPM)."""
    TabelaFrete.objects.create(nome="Maxxx", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("1"), no_checkout=True)
    respostas = {"awesomeapi": {"lat": "-22.8694657", "lng": "-43.2177078"},
                 "osrm": {"code": "Ok", "routes": [{"distance": 25224.9}]}}

    def api_lenta(url, timeout):
        if timeout < 1.5:  # a API responde em 1,5 s
            raise geo.GeoErro("timed out")
        if "project-osrm" in url:
            return respostas["osrm"]
        if "awesomeapi" in url:
            return respostas["awesomeapi"]
        raise geo.GeoErro("fora do ar")

    corpo = {"rate": {"destination": {"postal_code": "21941-806"}}}
    with patch.object(geo_rede, "_json", side_effect=api_lenta):
        geo.CoordenadaCep.objects.create(cep="01001000", latitude=Decimal("-23.55"),
                                         longitude=Decimal("-46.63"), fonte="teste")
        assert [o["total_price"] for o in opcoes_de_frete(corpo)] == ["2520"]


def test_cep_que_nada_localiza_cobra_o_valor_de_reserva_da_tabela():
    """Ultimo recurso: com o valor de reserva a opcao aparece; sem ele, a tabela some."""
    TabelaFrete.objects.create(nome="Com reserva", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("1"), no_checkout=True,
                               valor_reserva=Decimal("150.00"))
    TabelaFrete.objects.create(nome="Sem reserva", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("1"), no_checkout=True)
    with patch.object(geo_rede, "_json", side_effect=geo.GeoErro("fora do ar")):
        opcoes = opcoes_de_frete({"rate": {"destination": {"postal_code": "69900-000"}}})
    assert [(o["service_name"], o["total_price"]) for o in opcoes] == [("Com reserva", "15000")]


def test_erro_inesperado_numa_tabela_nao_tira_o_frete_das_outras():
    """Excecao fora do previsto virava 500 na view: a Shopify usava o backup rate."""
    _faixa(nome="Faixa boa")
    TabelaFrete.objects.create(nome="Quebrada", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("1"), no_checkout=True)
    with patch.object(geo, "km_entre_ceps", side_effect=RuntimeError("bug")):
        opcoes = opcoes_de_frete(CHECKOUT)
    assert [o["service_name"] for o in opcoes] == ["Faixa boa"]
