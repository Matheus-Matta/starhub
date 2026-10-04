from decimal import Decimal

import pytest
from django.db import transaction

from apps.core.origem import origem
from apps.loja.models import Categoria, Produto

from .envio_falso import configuracao


class Desfaz(Exception):
    pass


def _produto():
    # Nos testes de update o setup roda antes da configuracao existir: senao o create
    # do setup fica pendente na transacao do teste e absorve o update (dedupe).
    produto = Produto.objects.create(nome="Camiseta")
    return produto, produto.variantes.get()


@pytest.mark.django_db
def test_alteracao_vinda_do_shopify_vai_para_os_outros_e_nao_volta_ao_shopify(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """Sem excluir a origem, o webhook do Shopify gravava no hub e reenviava ao Shopify (laco)."""
    configuracao("falso")
    configuracao("shopify")

    with django_capture_on_commit_callbacks(execute=True), origem("shopify"):
        produto, _ = _produto()

    assert enfileirados == [("falso", "produtos", "create", str(produto.pk))]


@pytest.mark.django_db
def test_alteracao_feita_no_hub_vai_para_todos_os_marketplaces(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """Admin, API Woo e comando nao sao marketplace: nenhum destino pode ficar de fora."""
    configuracao("falso")
    configuracao("shopify")

    with django_capture_on_commit_callbacks(execute=True), origem("admin"):
        produto, _ = _produto()

    assert sorted(enfileirados) == [
        ("falso", "produtos", "create", str(produto.pk)),
        ("shopify", "produtos", "create", str(produto.pk)),
    ]


@pytest.mark.django_db
def test_configuracao_com_envio_desligado_nao_recebe(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """A matriz Enviar da tela e a vontade do lojista: desligado nao pode sair nada."""
    configuracao("falso", recursos=("categorias",))

    with django_capture_on_commit_callbacks(execute=True):
        _produto()

    assert enfileirados == []


@pytest.mark.django_db
def test_save_sem_mudanca_real_nao_envia(falsos, enfileirados, django_capture_on_commit_callbacks):
    """Salvar sem mudar nada (ou digitar "19.90" no lugar de 19.90) gastava chamada de API."""
    produto, variante = _produto()
    variante.price = Decimal("19.90")
    variante.save()
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True):
        produto.save()
        variante.price = "19.90"
        variante.save()

    assert enfileirados == []


@pytest.mark.django_db
def test_variante_que_so_mudou_estoque_envia_estoque_e_outra_mudanca_envia_o_produto_pai(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """Baixa de estoque nao pode reenviar o produto inteiro; preco novo nao e so estoque."""
    produto, variante = _produto()
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True):
        variante.inventory_quantity = 7
        variante.save()
    with django_capture_on_commit_callbacks(execute=True):
        variante.price = Decimal("29.90")
        variante.save()

    assert enfileirados == [
        ("falso", "estoque", "update", str(variante.pk)),
        ("falso", "produtos", "update", str(produto.pk)),
    ]


@pytest.mark.django_db
def test_excluir_no_hub_envia_delete(falsos, enfileirados, django_capture_on_commit_callbacks):
    """A exclusao em cascata (variantes antes do produto) tem que virar um delete so."""
    produto, _ = _produto()
    configuracao("falso")
    pk = str(produto.pk)

    with django_capture_on_commit_callbacks(execute=True):
        produto.delete()

    assert enfileirados == [("falso", "produtos", "delete", pk)]


@pytest.mark.django_db
def test_varias_gravacoes_do_mesmo_registro_na_transacao_viram_um_envio(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """O admin salva produto, variantes e produto de novo: eram tres tarefas iguais."""
    produto, _ = _produto()
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        for nome in ("A", "B", "C"):
            produto.nome = nome
            produto.save()

    assert enfileirados == [("falso", "produtos", "update", str(produto.pk))]


@pytest.mark.django_db
def test_rollback_nao_envia_e_nao_segura_o_proximo_envio(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """Enviar antes do commit mandava ao marketplace um dado que o hub desfez."""
    produto, _ = _produto()
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(Desfaz), transaction.atomic():
            produto.nome = "Desfeito"
            produto.save()
            raise Desfaz
        produto.nome = "Valido"
        produto.save()

    assert enfileirados == [("falso", "produtos", "update", str(produto.pk))]


@pytest.mark.django_db
def test_categoria_nova_no_produto_envia_o_produto(
    falsos, enfileirados, django_capture_on_commit_callbacks
):
    """O admin grava o M2M depois do save: so a categoria mudando nao passava pelo post_save."""
    produto, _ = _produto()
    categoria = Categoria.objects.create(nome="Verao", slug="verao")
    configuracao("falso")

    with django_capture_on_commit_callbacks(execute=True):
        produto.categorias.add(categoria)

    assert enfileirados == [("falso", "produtos", "update", str(produto.pk))]
