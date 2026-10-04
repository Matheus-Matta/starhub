"""Cadastro de tabela de frete: a tela muda pelo tipo e o servidor confere cada um."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.logistica import geo
from apps.logistica.models import FaixaCep, TabelaFrete

pytestmark = pytest.mark.django_db
ADD = "/admin/logistica/tabelafrete/add/"
VAZIO = {"faixas-TOTAL_FORMS": "0", "faixas-INITIAL_FORMS": "0"}


@pytest.fixture
def conta_do_form(conta):
    """Superusuario ve a secao Conta: o navegador manda conta e origem preenchidas."""
    return {"account": str(conta.pk), "origin": "starhub"}


def _faixas(*linhas):
    dados = {"faixas-TOTAL_FORMS": str(len(linhas)), "faixas-INITIAL_FORMS": "0"}
    for n, (inicio, fim, valor) in enumerate(linhas):
        dados |= {f"faixas-{n}-cep_inicial": inicio, f"faixas-{n}-cep_final": fim,
                  f"faixas-{n}-valor": valor}
    return dados


def test_tela_mostra_secao_de_distancia_e_faixas_conforme_o_tipo(admin_logado):
    html = admin_logado.get(ADD).content.decode()
    assert "secao-distancia" in html and 'id="faixas-group"' in html
    assert '"#faixas-group"' in html and '".secao-distancia"' in html  # regras do condicoes.js


def test_distancia_sem_cep_de_origem_e_recusada_no_servidor(admin_logado, conta_do_form):
    """Esconder o campo e so visual: sem CEP de origem a cotacao nao teria de onde medir."""
    resposta = admin_logado.post(ADD, {**conta_do_form, "nome": "Km", "tipo": "distancia",
                                       "prazo_dias": "1", "taxa_fixa": "0", "valor_minimo": "0",
                                       **VAZIO})
    assert resposta.status_code == 200
    assert "Informe o CEP de onde a entrega sai" in resposta.content.decode()
    assert not TabelaFrete.objects.exists()


def test_distancia_grava_o_cep_so_com_digitos(admin_logado, conta_do_form):
    admin_logado.post(ADD, {**conta_do_form, "nome": "Km", "tipo": "distancia",
                            "prazo_dias": "1", "cep_origem": "01001-000", "preco_por_km": "2.50",
                            "taxa_fixa": "0", "valor_minimo": "0", **VAZIO})
    assert TabelaFrete.objects.get().cep_origem == "01001000"


def test_faixas_que_se_cruzam_sao_recusadas(admin_logado, conta_do_form):
    """Duas faixas para o mesmo CEP: o lojista nao saberia qual valor o cliente paga."""
    resposta = admin_logado.post(ADD, {**conta_do_form, "nome": "SP", "tipo": "faixa_cep",
                                       "prazo_dias": "3", "taxa_fixa": "0", "valor_minimo": "0",
                                       **_faixas(("01000-000", "05999-999", "15"),
                                                 ("05000-000", "08999-999", "20"))})
    assert "se cruzam" in resposta.content.decode()
    assert not TabelaFrete.objects.exists()


def test_faixa_cep_sem_faixa_e_recusada_e_com_faixa_grava(admin_logado, conta_do_form):
    base = {**conta_do_form, "nome": "SP", "tipo": "faixa_cep", "prazo_dias": "3",
            "taxa_fixa": "0", "valor_minimo": "0"}
    assert "ao menos uma faixa" in admin_logado.post(ADD, {**base, **VAZIO}).content.decode()
    admin_logado.post(ADD, {**base, **_faixas(("01000-000", "05999-999", "15"))})
    faixa = FaixaCep.objects.get()
    assert (faixa.cep_inicial, faixa.cep_final, faixa.valor) == ("01000000", "05999999",
                                                                 Decimal("15.00"))


def test_simular_mostra_valor_prazo_e_km(admin_logado):
    tabela = TabelaFrete.objects.create(
        nome="Km", tipo="distancia", cep_origem="01001000", preco_por_km=Decimal("2"),
        prazo_dias=2)
    url = reverse("admin:logistica_tabelafrete_simular", args=[tabela.pk])
    with patch.object(geo, "km_entre_ceps", lambda *args: (Decimal("432.8"), True)):
        html = admin_logado.get(url, {"cep": "20040-020"}).content.decode()
    assert "R$ 865,60" in html and "432.8 km" in html and "2 dias uteis" in html
    assert "Simular cotacao" in admin_logado.get(
        reverse("admin:logistica_tabelafrete_change", args=[tabela.pk])).content.decode()
