"""Cotacao de frete: por distancia (km) e por faixa de CEP."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.logistica import geo
from apps.logistica.cotacao import FreteIndisponivel, cotar
from apps.logistica.models import FaixaCep, TabelaFrete

pytestmark = pytest.mark.django_db


def _distancia(**campos):
    padrao = {"nome": "Entrega propria", "tipo": "distancia", "cep_origem": "01001000",
              "preco_por_km": Decimal("2.35"), "taxa_fixa": Decimal("10.00"),
              "valor_minimo": Decimal("25.00"), "prazo_dias": 2}
    return TabelaFrete.objects.create(**{**padrao, **campos})


def _com_km(km, exata=True):
    return patch.object(geo, "km_entre_ceps", lambda *args: (Decimal(km), exata))


def test_distancia_cobra_taxa_mais_km_arredondado_ao_centavo():
    """12,3 km x R$ 2,35 = 28,905 -> 28,91 (meio para cima) + 10,00 de taxa = 38,91."""
    with _com_km("12.3"):
        cotacao = cotar(_distancia(), "20040-020")
    assert cotacao.valor == Decimal("38.91") and cotacao.prazo_dias == 2
    assert cotacao.distancia_km == Decimal("12.3") and "por estrada" in cotacao.detalhe


def test_entrega_perto_respeita_o_valor_minimo():
    with _com_km("1.0"):
        assert cotar(_distancia(), "01002000").valor == Decimal("25.00")


def test_acima_da_distancia_maxima_nao_entrega():
    with _com_km("80.4"), pytest.raises(FreteIndisponivel, match="distancia maxima de 50"):
        cotar(_distancia(distancia_maxima_km=Decimal("50")), "13000000")


def test_estimativa_sem_rota_aparece_no_detalhe():
    with _com_km("40.0", exata=False):
        assert "estimados" in cotar(_distancia(), "13000000").detalhe


def test_cep_sem_coordenada_vira_frete_indisponivel_com_o_motivo():
    def sem_local(origem, destino, *args):
        raise geo.GeoErro(f"Nao foi possivel localizar o CEP {destino}")

    with patch.object(geo, "km_entre_ceps", sem_local), pytest.raises(FreteIndisponivel,
                                                                   match="localizar"):
        cotar(_distancia(), "99999999")


def _faixas(*faixas, prazo=5):
    tabela = TabelaFrete.objects.create(nome="Tabela SP", tipo="faixa_cep", prazo_dias=prazo)
    for inicio, fim, valor, dias in faixas:
        FaixaCep.objects.create(tabela=tabela, cep_inicial=inicio, cep_final=fim,
                                valor=Decimal(valor), prazo_dias=dias)
    return tabela


def test_faixa_que_contem_o_cep_define_valor_e_prazo():
    tabela = _faixas(("01000000", "05999999", "15.00", 1), ("06000000", "09999999", "22.50", None))
    assert (cotar(tabela, "01001-000").valor, cotar(tabela, "01001000").prazo_dias) == (
        Decimal("15.00"), 1)
    # Faixa sem prazo usa o prazo da tabela.
    assert cotar(tabela, "07000000").prazo_dias == 5


def test_duas_faixas_com_o_cep_vale_a_mais_estreita():
    """Regra de excecao (um bairro dentro da cidade) tem que vencer a faixa geral."""
    tabela = _faixas(("01000000", "09999999", "20.00", None), ("01310000", "01310999", "35.00", 2))
    assert cotar(tabela, "01310-100").valor == Decimal("35.00")
    assert cotar(tabela, "01001-000").valor == Decimal("20.00")


@pytest.mark.parametrize("cep,motivo", [("123", "8 digitos"), ("80000000", "nenhuma faixa")])
def test_cep_invalido_ou_fora_das_faixas(cep, motivo):
    with pytest.raises(FreteIndisponivel, match=motivo):
        cotar(_faixas(("01000000", "09999999", "20.00", None)), cep)


def test_tabela_desativada_nao_cota():
    tabela = _faixas(("01000000", "09999999", "20.00", None))
    tabela.active = False
    with pytest.raises(FreteIndisponivel, match="desativada"):
        cotar(tabela, "01001000")
