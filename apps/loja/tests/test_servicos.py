"""Cadastro de servicos: nasce sozinho no pedido e da id e SKU ao ERP."""

import pytest
from django.db import IntegrityError

from apps.loja.models import Pedido, Servico
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.servicos import cadastrar_dos_pedidos, vincular

pytestmark = pytest.mark.django_db


def test_servico_novo_nasce_com_sku_gerado_e_o_repetido_reaproveita():
    primeiro = vincular([{"servico": "Montagem", "preco": "80.00"}])
    segundo = vincular([{"servico": "montagem ", "preco": "90.00"}])

    montagem = Servico.objects.get()
    assert montagem.sku == "SERV-MONTAGEM"
    assert primeiro[0]["servico_id"] == segundo[0]["servico_id"] == montagem.pk


def test_banco_recusa_dois_cadastros_com_o_mesmo_nome():
    """Dois pedidos chegando juntos: o indice unico segura, nao um if."""
    Servico.objects.create(nome="Montagem")
    with pytest.raises(IntegrityError):
        Servico.objects.create(nome="MONTAGEM", sku="OUTRO")


def test_migration_cadastra_os_servicos_dos_pedidos_antigos_uma_vez(conta):
    for servico in ("Montagem", "Garantia estendida", "montagem"):
        pedido = Pedido.objects.create()
        mesclar_extras(pedido, {"servicos": [{"item_id": 1, "servico": servico,
                                              "opcao": "Sim", "preco": "10.00"}]})
        pedido.save()

    assert cadastrar_dos_pedidos(Pedido, Servico) == 2
    assert cadastrar_dos_pedidos(Pedido, Servico) == 0
    assert sorted(Servico.objects.values_list("sku", flat=True)) == [
        "SERV-GARANTIA-ESTENDIDA", "SERV-MONTAGEM"]
