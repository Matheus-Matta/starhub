"""Foto de cada variacao do hub vira a imagem da variante no Shopify.

As fotos subiam para o produto, mas nenhuma era ligada a variante: na loja todas as
cores mostravam a foto principal.
"""

from decimal import Decimal

import pytest

from apps.loja.models import MidiaProduto, Produto, VarianteProduto
from apps.shopify.envio import produtos_midias_variantes
from apps.shopify.tests.test_envio_produto_religar import Sequencia
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador, _simples

pytestmark = pytest.mark.django_db
HUB = "https://hub.exemplo.com/media/produtos/"


def _gid(tipo, numero):
    return f"gid://shopify/{tipo}/{numero}"


def _pronta(*numeros, status="READY"):
    return {"nodes": [{"id": _gid("MediaImage", n), "status": status,
                       "image": {"url": f"https://cdn.shopify.com/{n}.png"}
                       if status == "READY" else None} for n in numeros]}


def _sofa():
    produto = Produto.objects.create(nome="Sofa", tipo=Produto.Tipo.VARIAVEL)
    MidiaProduto.objects.create(produto=produto, url=HUB + "sofa.png", posicao=0)
    for posicao, cor in enumerate(["Bege", "Prata"], 1):
        variante = VarianteProduto.objects.create(
            produto=produto, titulo=cor, sku=f"SOFA-{cor}", price=Decimal("10"),
            posicao=posicao, manage_inventory=False)
        MidiaProduto.objects.create(produto=produto, variante=variante, posicao=posicao,
                                    url=f"{HUB}sofa-{cor}.png")
    return produto


def _set():
    return {"productSet": {"product": {
        "id": PRODUTO_GID,
        "media": {"nodes": [{"id": _gid("MediaImage", n)} for n in (70, 71, 72)]},
        "variants": {"nodes": [
            {"id": _gid("ProductVariant", n), "position": n,
             "inventoryItem": {"id": _gid("InventoryItem", n)}} for n in (1, 2)]},
    }, "userErrors": []}}


def _ligadas(enviador):
    return [v["variants"] for q, v in enviador.cliente.chamadas
            if "productVariantsBulkUpdate" in q]


def _enviar(conta, respostas, produto):
    enviador = _enviador(conta, {})
    enviador._cliente = Sequencia({
        "productSet": _set(), "publications(": {"publications": {"nodes": []}},
        "productVariantsBulkUpdate": {"productVariantsBulkUpdate": {
            "productVariants": [], "userErrors": []}}, **respostas})
    enviador.criar(produto)
    return enviador


def test_cada_variacao_recebe_a_sua_foto_e_o_produto_fica_com_a_principal(conta):
    enviador = _enviar(conta, {"nodes(ids": _pronta(70, 71, 72)}, _sofa())

    assert _ligadas(enviador) == [[
        {"id": _gid("ProductVariant", 1), "mediaId": _gid("MediaImage", 71)},
        {"id": _gid("ProductVariant", 2), "mediaId": _gid("MediaImage", 72)},
    ]]


def test_foto_ainda_processando_espera_ficar_pronta(conta, monkeypatch):
    """O Shopify recusa ligar midia que nao esta pronta; logo apos o envio ela esta
    PROCESSING."""
    monkeypatch.setattr(produtos_midias_variantes, "ESPERA", 0)
    processando = _pronta(70, 71, 72, status="PROCESSING")
    enviador = _enviar(conta, {"nodes(ids": [processando, processando, _pronta(71, 72)]},
                       _sofa())

    [variantes] = _ligadas(enviador)
    assert [v["mediaId"] for v in variantes] == [_gid("MediaImage", 71),
                                                  _gid("MediaImage", 72)]


def test_foto_que_nao_fica_pronta_nao_derruba_o_envio(conta, monkeypatch):
    """Sem isso o produto ja criado na loja ficava sem vinculo e o proximo envio
    duplicava o produto."""
    monkeypatch.setattr(produtos_midias_variantes, "ESPERA", 0)
    processando = _pronta(70, 71, 72, status="PROCESSING")
    enviador = _enviar(conta, {"nodes(ids": [processando] * 10}, _sofa())

    assert _ligadas(enviador) == []


def test_mesma_url_na_variacao_e_no_produto_usa_a_midia_ja_enviada(conta):
    """A foto principal repetida na variacao e uma midia so na loja (produtos_midias)."""
    produto = _sofa()
    bege = produto.variantes.get(titulo="Bege")
    bege.midias.update(url=HUB + "sofa.png")
    enviador = _enviador(conta, {})
    enviador._cliente = Sequencia({
        "productSet": {"productSet": {**_set()["productSet"], "product": {
            **_set()["productSet"]["product"],
            "media": {"nodes": [{"id": _gid("MediaImage", n)} for n in (70, 72)]}}}},
        "publications(": {"publications": {"nodes": []}}, "nodes(ids": _pronta(70, 72),
        "productVariantsBulkUpdate": {"productVariantsBulkUpdate": {
            "productVariants": [], "userErrors": []}}})

    enviador.criar(produto)

    assert _ligadas(enviador) == [[
        {"id": _gid("ProductVariant", 1), "mediaId": _gid("MediaImage", 70)},
        {"id": _gid("ProductVariant", 2), "mediaId": _gid("MediaImage", 72)},
    ]]


def test_simples_nao_liga_foto_a_variante(conta):
    produto, _variante = _simples()
    MidiaProduto.objects.create(produto=produto, url=HUB + "mesa.png")
    enviador = _enviador(conta, {})
    enviador._cliente = Sequencia({
        "productSet": _set(), "publications(": {"publications": {"nodes": []}},
        "nodes(ids": _pronta(70), "location": {"location": {"id": _gid("Location", 1)}}})

    enviador.criar(produto)

    assert _ligadas(enviador) == []
