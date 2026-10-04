"""Frete do StarHub no checkout da Shopify: cotacao, rota assinada e o pedido."""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.logistica import geo
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


def test_rota_sem_assinatura_valida_ou_loja_desconhecida_e_recusada(client, conta):
    """Sem conferir o HMAC qualquer um descobriria a tabela de precos da loja."""
    configuracao = _configuracao(conta)
    assert _post(client, configuracao, CHECKOUT, assinatura="falsa").status_code == 401
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
