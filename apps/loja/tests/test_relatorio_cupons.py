"""Relatorio "Uso de cupons": cada uso com a data do pedido e o resumo por cupom."""

from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.loja.models import Pedido

pytestmark = pytest.mark.django_db
URL = reverse("admin:relatorio", args=["uso-cupons"]) + "?de=2026-09-01&ate=2026-09-30"


def _pedido(numero, dia, cupons, total="100.00", **campos):
    pedido = Pedido.objects.create(
        number=numero, total=Decimal(total), email=f"{numero}@cliente.test",
        linhas_cupom=[{"id": i, "code": c, "discount": d, "discount_tax": "0.00", "meta_data": []}
                      for i, (c, d) in enumerate(cupons, start=1)],
        **campos,
    )
    quando = timezone.make_aware(datetime(2026, 9 if dia else 1, dia or 10, 15, 0))
    Pedido.objects.filter(pk=pedido.pk).update(created_at=quando)
    return pedido


def _planilha(cliente):
    livro = load_workbook(BytesIO(cliente.get(URL + "&formato=xlsx").content))
    return [list(linha) for linha in livro["Usos"].values], list(livro["Resumo"].values)


def test_cada_uso_vira_uma_linha_com_a_data_do_pedido(admin_logado):
    _pedido("1001", 5, [("BLACK10", "10.05")])
    _pedido("1002", 6, [("BLACK10", "9.95"), ("FRETEGRATIS", "20.00")], total="80.00")
    _pedido("1003", 7, [])  # pedido sem cupom nao entra
    _pedido("1004", None, [("BLACK10", "5.00")])  # janeiro: fora do periodo

    usos, _ = _planilha(admin_logado)

    cabecalho, *linhas = usos
    assert cabecalho[:3] == ["Data de uso", "Cupom", "Pedido"]
    assert [(linha[1], linha[2]) for linha in linhas] == [
        ("BLACK10", "1001"), ("BLACK10", "1002"), ("FRETEGRATIS", "1002")]
    assert linhas[0][0] == datetime(2026, 9, 5, 15, 0)
    assert Decimal(str(linhas[0][cabecalho.index("Desconto")])) == Decimal("10.05")


def test_resumo_soma_usos_e_descontos_por_cupom(admin_logado):
    _pedido("1001", 5, [("BLACK10", "10.05")])
    _pedido("1002", 6, [("black10", "9.95")])  # o cliente digitou em minusculas

    _, resumo = _planilha(admin_logado)

    cabecalho, *linhas = resumo
    assert cabecalho[:3] == ("Cupom", "Usos", "Desconto total")
    assert len(linhas) == 1
    assert linhas[0][1] == 2
    assert Decimal(str(linhas[0][2])) == Decimal("20.00")


def test_data_de_uso_e_a_do_pedido_na_loja_e_nao_a_da_importacao(admin_logado):
    """Pedido importado em outubro, feito em setembro: o uso foi em setembro."""
    pedido = _pedido("1001", None, [("BLACK10", "10.00")])
    Pedido.objects.filter(pk=pedido.pk).update(
        placed_at=timezone.make_aware(datetime(2026, 9, 20, 9, 30)))

    usos, _ = _planilha(admin_logado)

    assert usos[1][0] == datetime(2026, 9, 20, 9, 30)


def test_pagina_mostra_o_resumo_e_os_usos(admin_logado):
    _pedido("1001", 5, [("BLACK10", "10.05")])

    html = admin_logado.get(URL).content.decode()

    assert "BLACK10" in html and "1001" in html
    assert "R$ 10,05" in html
