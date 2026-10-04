"""Migracao: pedido de marketplace com o numero da loja em number ganha numero do hub."""

import importlib
import re

import pytest
from django.apps import apps

from apps.core.models import Origin
from apps.loja.models import Pedido

migracao = importlib.import_module("apps.loja.migrations.0014_pedido_numero_do_hub")
NUMERO_DO_HUB = re.compile(r"^SH-[0-9A-F]{10}$")


def _numeros(pedido):
    pedido.refresh_from_db()
    return pedido.number, pedido.external_number


@pytest.mark.django_db
def test_migracao_move_o_numero_da_loja_para_external_number():
    """Pedido importado antes da regra ficava com #1001 em number, igual ao da loja."""
    sem_externo = Pedido.objects.create(number="1001", origin=Origin.SHOPIFY)
    com_externo = Pedido.objects.create(
        number="1002", external_number="1002", origin=Origin.SHOPIFY
    )

    migracao.numero_do_hub(apps, None)

    numero, externo = _numeros(sem_externo)
    assert NUMERO_DO_HUB.match(numero) and externo == "1001"
    numero, externo = _numeros(com_externo)
    assert NUMERO_DO_HUB.match(numero) and externo == "1002"


@pytest.mark.django_db
@pytest.mark.parametrize("origem", [Origin.STARHUB, Origin.API, Origin.IMPORT])
def test_migracao_nao_mexe_em_pedido_que_nasceu_no_hub(origem):
    """Pedido do hub ou do ERP ja tem o numero do hub; trocar quebraria o que o ERP guardou."""
    pedido = Pedido.objects.create(number="ERP-77", origin=origem)

    migracao.numero_do_hub(apps, None)

    assert _numeros(pedido) == ("ERP-77", "")


@pytest.mark.django_db
def test_migracao_nao_troca_quem_ja_tem_numero_do_hub():
    """Rodar de novo (ou pedido novo do importador) nao pode gerar outro numero."""
    pedido = Pedido.objects.create(number="SH-0A1B2C3D4E", external_number="1001",
                                   origin=Origin.SHOPIFY)

    migracao.numero_do_hub(apps, None)

    assert _numeros(pedido) == ("SH-0A1B2C3D4E", "1001")


@pytest.mark.django_db
def test_migracao_gera_outro_numero_quando_o_sorteado_ja_existe(monkeypatch):
    """O indice (conta, numero) derrubaria a migracao inteira num sorteio repetido."""
    Pedido.objects.create(number="SH-AAAAAAAAAA", origin=Origin.STARHUB)
    pedido = Pedido.objects.create(number="1001", origin=Origin.SHOPIFY)
    sorteios = iter(["AAAAAAAAAA", "BBBBBBBBBB"])
    monkeypatch.setattr(migracao, "_sorteio", lambda: next(sorteios))

    migracao.numero_do_hub(apps, None)

    assert _numeros(pedido) == ("SH-BBBBBBBBBB", "1001")
