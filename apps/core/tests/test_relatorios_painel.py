"""Relatorio no padrao do Painel: mini cards, graficos (Chart.js) e a lista direta."""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.loja.models import Pedido, Tag

pytestmark = pytest.mark.django_db


def _url(chave, query="?de=2026-09-01&ate=2026-09-30"):
    return reverse("admin:relatorio", args=[chave]) + query


def _em(modelo, obj, dia):
    modelo.objects.filter(pk=obj.pk).update(
        created_at=timezone.make_aware(datetime(2026, 9, dia, 15, 0)))


def _indicadores(resposta):
    return {item["rotulo"]: item for item in resposta.context["indicadores"]}


def _graficos(resposta):
    return {item["titulo"]: item for item in resposta.context["graficos"]}


@pytest.fixture
def pedidos():
    for numero, dia, total, status in (("1", 5, "100.00", "completed"),
                                       ("2", 5, "50.50", "pending"),
                                       ("3", 20, "200.00", "completed")):
        _em(Pedido, Pedido.objects.create(number=numero, total=Decimal(total), status=status), dia)


def test_mini_cards_mostram_total_media_e_soma_em_reais(admin_logado, pedidos):
    resposta = admin_logado.get(_url("loja.pedido"))

    cards = _indicadores(resposta)
    assert cards["Registros no periodo"]["valor"] == 3
    assert cards["Media por dia"]["valor"] == "0,1"  # 3 em 30 dias
    soma = cards["Soma de total"]
    assert (soma["valor"], soma["eh_moeda"]) == (Decimal("350.50"), True)


def test_pedido_com_varios_itens_conta_e_soma_uma_vez(admin_logado):
    """A lista de pedidos junta os itens (coluna "itens"): agrupado assim, o pedido de
    3 itens contava 3 vezes no grafico e somava o total 3 vezes."""
    pedido = Pedido.objects.create(number="1", total=Decimal("100.00"), status="completed")
    for _ in range(3):
        pedido.itens.create(nome="Caneca", quantidade=1, total=Decimal("33.33"))
    _em(Pedido, pedido, 5)

    resposta = admin_logado.get(_url("loja.pedido"))

    cards, graficos = _indicadores(resposta), _graficos(resposta)
    assert cards["Registros no periodo"]["valor"] == 1
    assert cards["Soma de total"]["valor"] == Decimal("100.00")
    assert sum(graficos["Novos por dia"]["series"][0]["dados"]) == 1
    assert graficos["Por status"]["series"][0]["dados"] == [1]
    assert cards["Media por dia"]["detalhe"] == "pico: 1 em 05/09"


def test_graficos_por_dia_e_por_status_com_os_numeros_do_periodo(admin_logado, pedidos):
    graficos = _graficos(admin_logado.get(_url("loja.pedido")))

    por_dia = graficos["Novos por dia"]
    assert len(por_dia["rotulos"]) == 30  # todo dia do periodo, inclusive os sem registro
    assert por_dia["rotulos"][4] == "05/09"
    assert por_dia["series"][0]["dados"][4] == 2 and sum(por_dia["series"][0]["dados"]) == 3

    status = graficos["Por status"]
    assert dict(zip(status["rotulos"], status["series"][0]["dados"], strict=True)) == {
        "Concluido": 2, "Pendente": 1}

    receita = graficos["Total por dia"]
    assert receita["moeda"] is True
    assert receita["series"][0]["dados"][19] == "200.00"  # texto: o JS nao arredonda centavo


def test_pagina_entrega_os_graficos_ao_chart_js_e_a_lista_fora_de_card(admin_logado, pedidos):
    html = admin_logado.get(_url("loja.pedido")).content.decode()

    assert 'id="relatorio-graficos"' in html
    assert "starhub/vendor/chart.umd.min.js" in html
    # A lista e a mesma da tela de listagem do admin: list-card, nao card com tabela dentro.
    lista = html.split('<section class="list-card')[-1]
    assert "<table" in lista and 'class="card' not in lista.split("<table")[0]


def test_graficos_vao_para_o_js_como_json_valido(admin_logado, pedidos):
    html = admin_logado.get(_url("loja.pedido")).content.decode()

    bruto = html.split('id="relatorio-graficos"')[1].split(">", 1)[1].split("</script>")[0]
    assert {g["titulo"] for g in json.loads(bruto)} >= {"Novos por dia", "Por status"}


def test_periodo_longo_agrupa_por_mes(admin_logado):
    _em(Tag, Tag.objects.create(nome="Antiga"), 10)

    graficos = _graficos(admin_logado.get(_url("loja.tag", "?de=2026-01-01&ate=2026-12-31")))

    assert graficos["Novos por mes"]["rotulos"][0] == "01/2026"
    assert len(graficos["Novos por mes"]["rotulos"]) == 12


def test_subitens_do_menu_de_relatorios_nao_tem_icone(admin_logado):
    html = admin_logado.get(reverse("admin:index")).content.decode()

    submenu = html.split('class="menu-sub"')[1].split("</details>")[0]
    assert "Pedidos" in submenu and "<svg" not in submenu
