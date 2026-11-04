"""Orientacao para publicar no Shopify os cupons cadastrados no StarHub."""

import pytest
from django.urls import reverse

URL = "/admin/integracoes/configuracaointegracao/shopify/"


@pytest.mark.django_db
def test_pagina_shopify_explica_como_publicar_cupons_do_hub(admin_logado):
    """Sem o escopo e o caminho de exportacao, o recurso existe mas nao e utilizavel."""
    html = admin_logado.get(URL).content.decode()

    assert "Cupons no checkout" in html
    assert "write_discounts" in html
    assert "/admin/loja/cupom/" in html
    assert "Sincronizar loja" in html
    assert reverse("admin:integracoes_cupons_guia") in html


@pytest.mark.django_db
def test_guia_de_cupons_explica_app_escopos_matriz_e_limites(admin_logado):
    html = admin_logado.get(reverse("admin:integracoes_cupons_guia")).content.decode()

    assert "Guia dos cupons na Shopify" in html
    assert "Desenvolver apps" in html
    assert "read_discounts" in html and "write_discounts" in html
    assert "Enviar" in html and "Cupons" in html and "Sincronizar loja" in html
    assert "Shopify Function" in html
