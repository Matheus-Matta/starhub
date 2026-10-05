"""Frete do hub no WooCommerce: zonas de entrega a partir das tabelas por faixa de CEP."""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.core.origem import origem
from apps.integracoes.models import ExecucaoIntegracao
from apps.logistica.models import FaixaCep, TabelaFrete
from apps.logistica.sinais import tabelas_alteradas
from apps.woocommerce.contexto import coletando_avisos
from apps.woocommerce.frete import zonas_desejadas
from apps.woocommerce.frete_envio import enviar_frete, frete_ligado, remover_frete
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao

pytestmark = pytest.mark.django_db


def _tabela(nome, faixas, prazo=0, **extra):
    tabela = TabelaFrete.objects.create(nome=nome, tipo=TabelaFrete.Tipo.FAIXA_CEP,
                                        prazo_dias=prazo, no_checkout=True, **extra)
    for inicio, fim, valor in faixas:
        FaixaCep.objects.create(tabela=tabela, cep_inicial=inicio, cep_final=fim,
                                valor=Decimal(valor))
    return tabela


def _resumo(zonas):
    return [(z["inicio"], z["fim"], [(m["titulo"], m["custo"]) for m in z["metodos"]])
            for z in zonas]


def test_faixas_sobrepostas_de_tabelas_diferentes_aparecem_juntas():
    """O Woo usa uma zona por CEP: zona por faixa esconderia uma das tabelas."""
    _tabela("Economica", [("01000000", "01999999", "10")], prazo=5)
    _tabela("Expressa", [("01500000", "02999999", "20")])

    zonas, avisos = zonas_desejadas()

    assert not avisos
    assert _resumo(zonas) == [
        ("01000000", "01499999", [("Economica (5 dias uteis)", "10.00")]),
        ("01500000", "01999999", [("Economica (5 dias uteis)", "10.00"), ("Expressa", "20.00")]),
        ("02000000", "02999999", [("Expressa", "20.00")]),
    ]


def test_dentro_da_tabela_vale_a_faixa_mais_estreita_como_no_hub():
    _tabela("Geral", [("01000000", "09999999", "30"), ("01000000", "01999999", "10")])

    zonas, _ = zonas_desejadas()

    assert _resumo(zonas) == [("01000000", "01999999", [("Geral", "10.00")]),
                              ("02000000", "09999999", [("Geral", "30.00")])]


def test_tabela_por_distancia_fica_fora_com_aviso():
    TabelaFrete.objects.create(nome="Motoboy", tipo=TabelaFrete.Tipo.DISTANCIA,
                               no_checkout=True, cep_origem="01001000",
                               preco_por_km=Decimal("2"))

    zonas, avisos = zonas_desejadas()

    assert zonas == [] and "Motoboy" in avisos[0]


def test_envio_troca_so_as_zonas_do_starhub(conta, monkeypatch):
    _tabela("Expressa", [("01000000", "01999999", "19.9")])
    loja = LojaFalsa({"shipping/zones": [
        {"id": 7, "name": "StarHub 03000000-03999999"}, {"id": 8, "name": "Sul (manual)"}],
    }).instalar(monkeypatch)
    cfg = configuracao(conta)

    with coletando_avisos():
        enviar_frete(cfg, lambda *_: None)

    escritas = [(m, r, c) for m, r, c in loja.chamadas if m != "GET"]
    zona = next(c for m, r, c in escritas if r == "shipping/zones")
    assert zona == {"name": "StarHub 01000000-01999999"}
    locais = next(c for m, r, c in escritas if r.endswith("/locations"))
    assert locais == [{"code": "01000000...01999999", "type": "postcode"}]
    metodo = next(c for m, r, c in escritas if r.endswith("/methods"))
    assert metodo["method_id"] == "flat_rate" and metodo["settings"]["cost"] == "19.90"
    assert ("DELETE", "shipping/zones/7", None) in escritas
    assert not any(r == "shipping/zones/8" for _, r, _ in escritas), "zona manual fica"
    assert frete_ligado(cfg)


def test_desligar_remove_as_zonas_e_a_marca(conta, monkeypatch):
    loja = LojaFalsa({"shipping/zones": [{"id": 7, "name": "StarHub 01000000-01999999"}]}
                     ).instalar(monkeypatch)
    cfg = configuracao(conta)
    enviar_frete(cfg, lambda *_: None)

    remover_frete(cfg, lambda *_: None)

    assert ("DELETE", "shipping/zones/7", None) in loja.chamadas and not frete_ligado(cfg)


@pytest.fixture
def fila(monkeypatch):
    chamadas = []
    monkeypatch.setattr("apps.woocommerce.frete_sinais.enfileirar",
                        lambda tarefa, *args: chamadas.append(args) or type("R", (), {"id": "x"}))
    return chamadas


def test_mudar_tabelas_com_frete_ligado_reenvia_uma_vez_por_commit(
        conta, monkeypatch, fila, django_capture_on_commit_callbacks):
    """Apagar uma tabela dispara um sinal por faixa: so um reenvio pode ficar na fila."""
    LojaFalsa().instalar(monkeypatch)
    cfg = configuracao(conta)
    enviar_frete(cfg, lambda *_: None)

    with django_capture_on_commit_callbacks() as agendados, transaction.atomic():
        _tabela("Expressa", [("01000000", "01999999", "10"), ("02000000", "02999999", "20")])

    assert len(agendados) == 1
    agendados[0]()
    assert len(fila) == 1
    assert ExecucaoIntegracao.objects.get().parametros == {"remover": False}


def test_sem_frete_ligado_nada_e_enviado(conta, fila, django_capture_on_commit_callbacks):
    configuracao(conta)

    with django_capture_on_commit_callbacks(execute=True):
        _tabela("Expressa", [("01000000", "01999999", "10")])

    assert fila == []


def test_importacao_de_planilha_reenvia_so_no_fim(
        conta, monkeypatch, fila, django_capture_on_commit_callbacks):
    """Uma planilha de 500 faixas nao pode enfileirar 500 reenvios."""
    LojaFalsa().instalar(monkeypatch)
    enviar_frete(configuracao(conta), lambda *_: None)

    # A lista do capture so e preenchida na saida do bloco: um bloco por etapa.
    with django_capture_on_commit_callbacks() as por_linha, origem("importacao"):
        _tabela("Planilha", [("01000000", "01999999", "10")])
    with django_capture_on_commit_callbacks() as no_fim:
        tabelas_alteradas.send(sender=TabelaFrete)

    assert (len(por_linha), len(no_fim)) == (0, 1)
