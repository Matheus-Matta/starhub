"""Sprite de icones (static/starhub/img/icones.svg) visto pelo servidor."""

import re

import pytest

pytestmark = pytest.mark.django_db


def test_pagina_do_modal_sabe_o_endereco_do_sprite(admin_logado):
    """Sem menu nem cabecalho no modal, o JS pega o sprite do <html> para desenhar
    icones (imagens, tags); com versao, para o navegador nao usar a copia antiga."""
    html = admin_logado.get("/admin/loja/cliente/add/?_popup=1").content.decode()
    sprite = re.search(r'<html[^>]* data-sprite="([^"]+)"', html).group(1)
    assert re.fullmatch(r"/static/starhub/img/icones\.svg\?v=\d+", sprite)
    assert f'href="{sprite}#' in html or "svg.icon" not in html
