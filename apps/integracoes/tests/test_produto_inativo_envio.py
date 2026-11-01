"""Produto inativo (ex.: criado pelo ERP) nao vai a loja nenhuma; ativado, vai."""

import pytest

from apps.core.origem import origem
from apps.loja.models import Produto

from .envio_falso import configuracao
from .test_envio_tarefa import _enviar

pytestmark = pytest.mark.django_db


def test_produto_inativo_e_o_estoque_dele_nao_entram_na_fila(
        falsos, enfileirados, django_capture_on_commit_callbacks):
    """O produto que o ERP cria e so o essencial: nao pode aparecer na loja assim."""
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True), origem("woo_api"):
        produto = Produto.objects.create(nome="COMODA DUBAI", active=False)
        variante = produto.variantes.get()
        variante.sku, variante.inventory_quantity = "2065", 2
        variante.save()
        variante.inventory_quantity = 5
        variante.save()
        produto.categorias.set([])
        produto.nome = "COMODA DUBAI 6 GAVETAS"
        produto.save()

    assert enfileirados == []


def test_ativar_o_produto_manda_criar_nas_lojas(
        falsos, enfileirados, django_capture_on_commit_callbacks):
    produto = Produto.objects.create(nome="COMODA DUBAI", active=False)
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True), origem("admin"):
        produto.active = True
        produto.save()

    assert enfileirados == [("falso", "produtos", "update", str(produto.pk))]
    _enviar(configuracao("shopify"), "produtos", "update", produto.pk)  # sem vinculo: cria
    assert falsos == [("shopify", "criar", produto.pk)]


def test_envio_de_estoque_que_ja_estava_na_fila_e_ignorado(falsos):
    loja = configuracao("falso")
    produto = Produto.objects.create(nome="Inativo", active=False)

    resultado = _enviar(loja, "estoque", "update", produto.variantes.get().pk)

    assert falsos == [] and "inativo" in resultado["message"]
