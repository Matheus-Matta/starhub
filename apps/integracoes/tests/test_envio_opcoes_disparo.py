"""Trocar so a opcao da variante (Cor: Azul -> Verde) tem de enviar o produto.

ValorDaVarianteProduto nao estava no MAPA do distribuidor e o save da variante sem
outro campo mudado nao gerava envio: a loja ficava com a opcao antiga.
"""

import pytest

from apps.loja.models import Produto, TipoVariante, ValorDaVarianteProduto, ValorVariante

from .envio_falso import configuracao


def _com_opcao(valor):
    produto = Produto.objects.create(nome="Sofa")
    cor = TipoVariante.objects.create(nome="Cor")
    opcao = ValorDaVarianteProduto.objects.create(
        variante=produto.variantes.get(),
        valor=ValorVariante.objects.create(tipo=cor, valor=valor))
    return produto, cor, opcao


@pytest.mark.django_db
def test_trocar_a_opcao_da_variante_envia_o_produto(falsos, enfileirados,
                                                    django_capture_on_commit_callbacks):
    produto, cor, opcao = _com_opcao("Azul")
    verde = ValorVariante.objects.create(tipo=cor, valor="Verde")
    configuracao("shopify")

    with django_capture_on_commit_callbacks(execute=True):
        opcao.valor = verde
        opcao.save()

    assert enfileirados == [("shopify", "produtos", "update", str(produto.pk))]


@pytest.mark.django_db
def test_remover_a_opcao_da_variante_envia_o_produto(falsos, enfileirados,
                                                     django_capture_on_commit_callbacks):
    produto, _cor, opcao = _com_opcao("Azul")
    configuracao("shopify")

    with django_capture_on_commit_callbacks(execute=True):
        opcao.delete()

    assert enfileirados == [("shopify", "produtos", "update", str(produto.pk))]


@pytest.mark.django_db
def test_mudar_preco_da_variante_envia_o_produto(falsos, enfileirados,
                                                 django_capture_on_commit_callbacks):
    """O caso do pedido: valor da variante alterado tem de sair para a loja."""
    produto = Produto.objects.create(nome="Sofa")
    variante = produto.variantes.get()
    configuracao("shopify")

    with django_capture_on_commit_callbacks(execute=True):
        variante.price = 99
        variante.save()

    assert enfileirados == [("shopify", "produtos", "update", str(produto.pk))]
