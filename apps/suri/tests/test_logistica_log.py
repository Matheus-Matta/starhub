"""Corpo real do Suri na cotacao e os logs que explicam um frete vazio em prod."""

import json
import logging
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.logistica.models import FaixaCep, TabelaFrete
from apps.suri.frete import ligar_frete
from apps.suri.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db
AUTORIZACAO = {"HTTP_AUTHORIZATION": "Bearer token-teste"}

# Exemplo de body da documentacao de logistica do Suri, sem alteracao.
EXEMPLO_DO_SURI = {
    "Items": [
        {"Id": "ID-123", "SkuId": "SKU-123", "ProductName": "Rybelsus 7mg Com 30 Comp.",
         "Measures": {"WeightInGrams": 250.0, "HeightInCm": 10.5, "WidthInCm": 8.2,
                      "LengthInCm": 15.0, "UnitsPerPackage": 1},
         "ProductQuantity": 2},
        {"Id": "321", "SkuId": "3232141", "ProductName": "Ozempic 1mg",
         "Measures": {"WeightInGrams": 180.0, "HeightInCm": 9.0, "WidthInCm": 7.0,
                      "LengthInCm": 12.0, "UnitsPerPackage": 1},
         "ProductQuantity": 1},
    ],
    "Address": {"Name": "Casa", "State": "CE", "City": "Fortaleza",
                "Street": "Av. Monsenhor Tabosa", "Number": "1000", "ZipCode": "60165-010",
                "Neighborhood": "Praia de Iracema", "Complement": "Ap 101",
                "GeoCoordinates": [-3.721, -38.522]},
}


@pytest.fixture
def cfg(conta):
    cfg = configuracao(conta)
    ligar_frete(cfg, True)
    tabela = TabelaFrete.objects.create(nome="Economica", tipo=TabelaFrete.Tipo.FAIXA_CEP,
                                        prazo_dias=3, no_checkout=True)
    FaixaCep.objects.create(tabela=tabela, cep_inicial="60000000", cep_final="60999999",
                            valor=Decimal("19.90"))
    return cfg


def _postar(client, cfg, corpo):
    return client.post(reverse("suri_logistica", args=[cfg.uuid]), data=json.dumps(corpo),
                       content_type="application/json", **AUTORIZACAO)


def test_exemplo_da_documentacao_do_suri_e_cotado(client, cfg):
    resposta = _postar(client, cfg, EXEMPLO_DO_SURI)

    opcoes = json.loads(resposta.content, parse_float=Decimal)
    assert resposta.status_code == 200
    assert [(o["Name"], o["Price"], o["Type"]) for o in opcoes] == [
        ("Economica", Decimal("19.90"), 1)]


def test_cep_com_outra_caixa_no_nome_do_campo_e_cotado(client, cfg):
    """"zipCode" (camelCase do serializador .NET) virava CEP '' e o checkout ficava sem
    frete, so com "CEP '' invalido" no log."""
    corpo = {"items": [], "address": {"zipCode": "60165010", "city": "Fortaleza"}}

    assert len(_postar(client, cfg, corpo).json()) == 1


@override_settings(LOG_CORPO_INTEGRACOES=False)
def test_cep_ausente_loga_a_estrutura_sem_o_dado_do_cliente(client, cfg, caplog):
    """Sem o corpo no log nao havia como saber onde o Suri pos o CEP."""
    corpo = {"Items": [], "Address": {"Street": "Rua Sigilosa", "Cep": "60165010"}}

    with caplog.at_level(logging.INFO, logger="apps.suri.logistica_api"):
        resposta = _postar(client, cfg, corpo)

    assert resposta.json() == []
    assert '"Cep": "str"' in caplog.text
    assert "Rua Sigilosa" not in caplog.text


@override_settings(LOG_CORPO_INTEGRACOES=True)
def test_com_a_chave_ligada_o_corpo_e_as_opcoes_vao_para_o_log(client, cfg, caplog):
    with caplog.at_level(logging.INFO, logger="apps.suri.logistica_api"):
        _postar(client, cfg, EXEMPLO_DO_SURI)

    assert "Monsenhor Tabosa" in caplog.text
    assert "Economica=19.90" in caplog.text


def test_token_errado_loga_o_formato_sem_o_token(client, cfg, caplog):
    with caplog.at_level(logging.INFO, logger="apps.suri.logistica_api"):
        client.post(reverse("suri_logistica", args=[cfg.uuid]), data=b"{}",
                    content_type="application/json", HTTP_AUTHORIZATION="Bearer segredo1")

    assert "'Bearer <8 caracteres>'" in caplog.text
    assert "segredo1" not in caplog.text
