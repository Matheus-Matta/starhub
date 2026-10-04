"""Coluna "Acoes" das listagens: itens do pedido e variacoes do produto variavel abrem
abaixo da linha (conteudo ja vem no HTML), e a coluna de origem do pedido."""

import pytest

from apps.core.admin_utils import badge_origem
from apps.loja.models import (
    ItemPedido,
    MidiaProduto,
    Pedido,
    Produto,
    TipoVariante,
    ValorDaVarianteProduto,
    ValorVariante,
    VarianteProduto,
)
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


def test_listagem_de_pedidos_traz_os_itens_com_imagem_e_a_origem(admin_logado, conta):
    caneca = criar_produto("Caneca azul", sku="CAN-1", price=30)
    MidiaProduto.objects.create(produto=caneca, variante=caneca.variante_padrao,
                                url="/static/starhub/img/demos/demo1.png")
    pedido = Pedido.objects.create(origin="shopify")
    ItemPedido.objects.create(pedido=pedido, variante=caneca.variante_padrao, quantidade=2,
                              subtotal=60, total=60)
    html = admin_logado.get("/admin/loja/pedido/").content.decode()
    assert 'data-detalhe' in html and "Caneca azul" in html and "SKU: CAN-1" in html
    assert "/static/starhub/img/demos/demo1.png" in html
    assert 'fill="#7AB55C"' in html and "Shopify" in html  # icone e nome da origem


def test_listagem_de_produtos_so_abre_variacoes_do_variavel(admin_logado, conta):
    criar_produto("Caneca", sku="CAN-1")
    tenis = Produto.objects.create(nome="Tenis", tipo=Produto.Tipo.VARIAVEL)
    tenis.variantes.all().delete()
    cor = TipoVariante.objects.create(nome="Cor")
    variante = VarianteProduto.objects.create(produto=tenis, titulo="Preto", sku="TEN-P")
    ValorDaVarianteProduto.objects.create(
        variante=variante, valor=ValorVariante.objects.create(tipo=cor, valor="Preto")
    )
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    assert html.count("data-detalhe") == 1  # so o variavel
    assert "Cor: Preto" in html and "SKU: TEN-P" in html


def test_badge_de_origem_usa_simple_icons_e_loja_quando_nao_ha():
    assert "<svg" in badge_origem("woocommerce", "WooCommerce")
    loja = badge_origem("mercado_livre", "Mercado Livre")
    assert "#store" in loja and "Mercado Livre" in loja
    assert "starhub/img/marca-64.png" in badge_origem("starhub", "StarHub")
