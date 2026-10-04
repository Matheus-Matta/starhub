"""Frete no checkout: "pronto" so com os obrigatorios verdes; o Ligar avisa o que falta."""

import json
import re

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.logistica.models import TabelaFrete
from apps.shopify.frete_checklist import OBRIGATORIOS, checklist
from apps.shopify.tests.test_frete_cadastro import configuracao  # noqa: F401 (fixture)
from apps.shopify.tests.test_frete_diagnostico import _verificar

pytestmark = pytest.mark.django_db
PAGINA = "/admin/integracoes/configuracaointegracao/shopify/"


def test_pronto_com_os_obrigatorios_verdes_mesmo_com_aviso_opcional(configuracao):  # noqa: F811
    """Peso e embalagem nunca ficam verdes sozinhos: nao podem travar o "pronto"."""
    TabelaFrete.objects.create(nome="SP", tipo="faixa_cep", no_checkout=True)
    _verificar(configuracao)
    resultado = checklist(configuracao)
    obrigatorios, opcionais = (itens for _, itens in resultado["grupos"])
    assert [i["titulo"] for i in obrigatorios] == list(OBRIGATORIOS)
    assert {i["titulo"] for i in opcionais} >= {"Peso nos produtos", "Embalagem padrao"}
    assert resultado["pronto"] and resultado["selo"] == "Pronto para o checkout"
    assert resultado["para_ligar"] == []


def test_desligado_e_sem_verificar_lista_o_que_falta_para_ligar(configuracao):  # noqa: F811
    configuracao.frete_ativo = False
    resultado = checklist(configuracao)
    assert not resultado["pronto"] and resultado["selo"] == "Faltam 6 de 6 obrigatorios"
    faltas = resultado["para_ligar"]
    # Ligar e o proprio cadastro: ele nao aparece como pendencia do Ligar.
    assert not any(f.startswith("Frete do StarHub cadastrado") for f in faltas)
    assert any(f.startswith("Ligado a zona de envio: depois de ligar") for f in faltas)
    assert any(f.startswith("Tabelas de frete no checkout: Marque") for f in faltas)
    assert any("ainda nao verificado" in f for f in faltas)


def _ligar(html):
    botao = re.search(r'<button[^>]*value="frete_ativar"[^>]*>', html).group(0)
    dados = re.search(r'<script id="frete-para-ligar" type="application/json">(.*?)</script>',
                      html, re.S)
    return botao, json.loads(dados.group(1)) if dados else None


def test_ligar_com_pendencia_mostra_a_lista_no_dialogo(admin_logado, configuracao):  # noqa: F811
    ConfiguracaoIntegracao.objects.filter(pk=configuracao.pk).update(frete_ativo=False)
    html = admin_logado.get(PAGINA).content.decode()
    botao, faltas = _ligar(html)
    assert 'data-confirmar-lista="frete-para-ligar"' in botao
    assert 'data-confirmar-botao="Ligar mesmo assim"' in botao
    assert any(f.startswith("Tabelas de frete no checkout") for f in faltas)
    assert "Faltam 6 de 6 obrigatorios" in html and "Opcionais (so avisam)" in html


def test_ligar_com_tudo_pronto_nao_tem_lista(admin_logado, configuracao):  # noqa: F811
    TabelaFrete.objects.create(nome="SP", tipo="faixa_cep", no_checkout=True)
    _verificar(configuracao)
    ConfiguracaoIntegracao.objects.filter(pk=configuracao.pk).update(frete_ativo=False)
    botao, faltas = _ligar(admin_logado.get(PAGINA).content.decode())
    assert faltas == [] and "Tudo pronto" in botao and "data-confirmar-lista" not in botao
