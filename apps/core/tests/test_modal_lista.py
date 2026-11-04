"""Contrato do modal usado pelas listas de filhos do admin."""

from django.conf import settings


def test_modal_generico_funciona_em_pagina_sem_jquery():
    """Lista de filhos nao depende de widget relacionado para abrir o iframe."""
    caminho = settings.BASE_DIR / "static/starhub/js/modal-relacionado.js"
    javascript = caminho.read_text(encoding="utf-8")

    assert "if (!$) return" not in javascript
    assert "if ($)" in javascript
