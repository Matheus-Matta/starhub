"""Servico que entra sozinho no pedido: montagem gratis que o cliente esquece de marcar."""

from decimal import Decimal

import pytest

from apps.loja.models import ItemPedido, Pedido, RegraServico, Servico
from apps.loja.services.extras_pedido import extras, mesclar_extras
from apps.loja.services.servicos_automaticos import completar
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido():
    guarda_roupa = criar_produto("Guarda-roupa", sku="GR-1", price=Decimal("900.00"))
    mesa = criar_produto("Mesa", sku="ME-1", price=Decimal("300.00"))
    pedido = Pedido.objects.create()
    ItemPedido.objects.create(pedido=pedido, produto=guarda_roupa, nome="Guarda-roupa",
                              sku="GR-1", quantidade=2, subtotal=Decimal("1800.00"),
                              total=Decimal("1800.00"))
    ItemPedido.objects.create(pedido=pedido, produto=mesa, nome="Mesa", sku="ME-1",
                              subtotal=Decimal("300.00"), total=Decimal("300.00"))
    return pedido, guarda_roupa


def _montagem(produto, inclusao, preco_regra=Decimal("30.00"), **campos):
    servico = Servico.objects.create(nome="Montagem", sku="8875", preco=Decimal("10.00"),
                                     inclusao=inclusao, **campos)
    RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO,
                                preco=preco_regra).produtos.set([produto])
    return servico


def _servicos(pedido):
    pedido.refresh_from_db()
    return {(s["sku"], s["servico"]): s for s in extras(pedido).get("servicos", [])}


def test_regra_inclui_so_nos_itens_que_a_regra_pega_com_o_preco_da_regra(pedido):
    pedido, guarda_roupa = pedido
    servico = _montagem(guarda_roupa, Servico.Inclusao.REGRA)

    completar(pedido)

    servicos = _servicos(pedido)
    assert list(servicos) == [("GR-1", "Montagem")]
    assert servicos[("GR-1", "Montagem")] == {
        "item_id": pedido.itens.get(sku="GR-1").pk, "sku": "GR-1", "servico": "Montagem",
        "servico_id": servico.pk, "opcao": "Sim", "preco": "60.00", "automatico": True}


def test_todos_inclui_em_todo_item_e_fora_da_regra_vale_o_preco_padrao(pedido):
    pedido, guarda_roupa = pedido
    _montagem(guarda_roupa, Servico.Inclusao.TODOS)

    completar(pedido)

    servicos = _servicos(pedido)
    assert servicos[("GR-1", "Montagem")]["preco"] == "60.00"
    assert servicos[("ME-1", "Montagem")]["preco"] == "10.00"


def test_servico_automatico_nao_mexe_no_total_que_o_cliente_pagou(pedido):
    """O cliente nao pagou o servico na loja: somar no item desbateria o total."""
    pedido, guarda_roupa = pedido
    _montagem(guarda_roupa, Servico.Inclusao.TODOS)

    completar(pedido)

    assert sorted(pedido.itens.values_list("total", flat=True)) == [
        Decimal("300.00"), Decimal("1800.00")]
    assert not any(s.get("somado") for s in _servicos(pedido).values())


def test_so_quando_o_cliente_escolhe_ou_servico_inativo_nao_entra(pedido):
    pedido, guarda_roupa = pedido
    _montagem(guarda_roupa, Servico.Inclusao.ESCOLHA)
    Servico.objects.create(nome="Garantia", preco=Decimal("5.00"),
                           inclusao=Servico.Inclusao.TODOS, active=False)

    completar(pedido)

    assert _servicos(pedido) == {}


def test_servico_que_o_cliente_ja_escolheu_nao_repete(pedido):
    pedido, guarda_roupa = pedido
    servico = _montagem(guarda_roupa, Servico.Inclusao.REGRA)
    item = pedido.itens.get(sku="GR-1")
    escolhido = {"item_id": item.pk, "sku": "GR-1", "servico": "Montagem",
                 "servico_id": servico.pk, "opcao": "Sim", "preco": "45.00", "somado": True}
    mesclar_extras(pedido, {"servicos": [escolhido]})
    pedido.save()

    completar(pedido)

    assert list(_servicos(pedido).values()) == [escolhido]


def test_reimportar_nao_duplica_e_item_que_saiu_perde_o_servico(pedido):
    """O webhook reimporta o pedido varias vezes; o item pode sumir no meio."""
    pedido, guarda_roupa = pedido
    _montagem(guarda_roupa, Servico.Inclusao.TODOS)
    completar(pedido)
    completar(pedido)
    assert len(_servicos(pedido)) == 2

    pedido.itens.filter(sku="ME-1").delete()
    completar(pedido)

    assert list(_servicos(pedido)) == [("GR-1", "Montagem")]


def test_admin_grava_as_integracoes_escolhidas_no_multiselect(rf, admin_user):
    """Lista de plataformas no JSON: o form mostra multi-select, nunca o JSON cru."""
    from django.contrib import admin

    servico = Servico.objects.create(nome="Montagem", sku="8875")
    request = rf.get("/")
    request.user = admin_user
    form_class = admin.site._registry[Servico].get_form(request, servico)

    form = form_class(instance=servico, data={
        "nome": "Montagem", "sku": "8875", "preco": "0.00", "active": "on",
        "inclusao": "todos", "fora_das_integracoes": ["suri", "shopify"]})

    assert form.is_valid(), form.errors
    form.save()
    servico.refresh_from_db()
    assert (servico.inclusao, servico.fora_das_integracoes) == ("todos", ["suri", "shopify"])
    assert 'multiple' in str(form["fora_das_integracoes"])
