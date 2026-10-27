"""API que o Suri chama no checkout para buscar as opcoes de entrega do StarHub."""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.logistica.models import FaixaCep, TabelaFrete
from apps.suri.frete import ligar_frete
from apps.suri.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db


def _url(cfg):
    return reverse("suri_logistica", args=[cfg.uuid])


def _autorizacao(token="token-teste"):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _corpo(cep="60165-010"):
    return {"Items": [{"Id": "48349", "SkuId": "CAM-AZ", "ProductName": "Camiseta",
                       "Measures": {"WeightInGrams": 250}, "ProductQuantity": 2}],
            "Address": {"State": "CE", "City": "Fortaleza", "Street": "Rua A",
                        "Number": "10", "ZipCode": cep}}


def _tabela(nome="Economica", valor="12.50", prazo=4):
    tabela = TabelaFrete.objects.create(nome=nome, tipo=TabelaFrete.Tipo.FAIXA_CEP,
                                        prazo_dias=prazo, no_checkout=True)
    FaixaCep.objects.create(tabela=tabela, cep_inicial="60000000", cep_final="60999999",
                            valor=Decimal(valor))
    return tabela


def test_get_valida_o_endpoint_com_o_token_da_loja(client, conta):
    cfg = configuracao(conta)

    resposta = client.get(_url(cfg), **_autorizacao())

    assert resposta.status_code == 200 and resposta.json() == []
    assert client.get(_url(cfg)).status_code == 401
    assert client.get(_url(cfg), **_autorizacao("errado")).status_code == 401


def test_post_devolve_as_tabelas_no_contrato_shop_logistic(client, conta):
    cfg = configuracao(conta)
    ligar_frete(cfg, True)
    tabela = _tabela()

    resposta = client.post(_url(cfg), data=json.dumps(_corpo()),
                            content_type="application/json", **_autorizacao())

    assert resposta.status_code == 200
    opcoes = json.loads(resposta.content, parse_float=Decimal)
    assert opcoes == [{
        "ProviderId": f"HUB_{tabela.pk}", "Name": "Economica", "FromSellerId": "all",
        "Type": 1, "Price": Decimal("12.50"), "Description": "Faixa 60000000 a 60999999",
        "ListPrice": Decimal("12.50"), "PriceWithoutDiscount": Decimal("12.50"),
        "DiscountAmount": Decimal("0.00"), "CompanyName": "Economica",
        "MinShippingTimeEstimative": "4 dias uteis",
        "ShippingTimeEstimative": "4 dias uteis",
    }]
    assert b'"Price": 12.50' in resposta.content


def test_post_desligado_nao_cota_e_corpo_sem_cep_e_recusado(client, conta):
    cfg = configuracao(conta)
    _tabela()

    desligada = client.post(_url(cfg), data=json.dumps(_corpo()),
                             content_type="application/json", **_autorizacao())
    assert desligada.status_code == 204

    ligar_frete(cfg, True)
    invalida = client.post(_url(cfg), data=b"{}", content_type="application/json",
                           **_autorizacao())
    assert invalida.status_code == 400
    assert invalida.json()["error"] == "InvalidAddress"
