"""Sincronizar loja: busca tudo na loja e importa na ordem certa, com progresso."""

import pytest

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import argumentos
from apps.loja.models import Categoria, Cliente, Pedido, Produto
from apps.woocommerce.tasks import sincronizar_woocommerce
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao

pytestmark = pytest.mark.django_db
TUDO = tuple((r, "get") for r in ("categorias", "produtos", "clientes", "pedidos", "cupons"))


def _loja():
    filha = {"id": 10, "name": "Retrateis", "slug": "retrateis", "parent": 9}
    pai = {"id": 9, "name": "Sofas", "slug": "sofas", "parent": 0}
    return LojaFalsa({
        # A filha vem antes da pai: a pai e importada primeiro pelo mapa de todas.
        "products/categories": [filha, pai],
        "products": [exemplos.produto_simples(), exemplos.produto_variavel()],
        "products/20/variations": [exemplos.variacao(21, "Azul", "CAM-AZ", "49.90", 3)],
        "customers": [exemplos.cliente()],
        "orders": [exemplos.pedido()],
        "coupons": [{"id": 3, "code": "promo10", "discount_type": "percent", "amount": "10"}],
    })


def _execucao(cfg):
    return ExecucaoIntegracao.objects.create(configuracao=cfg,
                                             tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR)


def test_sincronizacao_importa_tudo_e_conclui_a_tarefa(conta, monkeypatch):
    loja = _loja().instalar(monkeypatch)
    execucao = _execucao(configuracao(conta, receber=TUDO))

    resultado = sincronizar_woocommerce(str(execucao.pk))

    execucao.refresh_from_db()
    assert resultado["status"] == ExecucaoIntegracao.Status.CONCLUIDA, execucao.falhas
    assert execucao.progresso == 100 and execucao.processados == 7
    assert Categoria.objects.get(slug="retrateis").pai.slug == "sofas"
    assert Produto.objects.count() == 2 and Cliente.objects.count() == 1
    assert Pedido.objects.get().itens.get().produto.nome == "Sofa Azul"
    assert ("LISTAR", "customers", {"role": "all"}) in loja.chamadas


def test_item_que_quebra_vira_falha_e_os_outros_entram(conta, monkeypatch):
    loja = _loja().instalar(monkeypatch)
    loja.colecoes["products"].insert(0, {"id": 99, "type": "simple", "stock_quantity": "muitos"})
    execucao = _execucao(configuracao(conta, receber=(("produtos", "get"),)))

    sincronizar_woocommerce(str(execucao.pk))

    execucao.refresh_from_db()
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
    assert execucao.falhas[0]["id_externo"] == "99"
    assert Produto.objects.count() == 2


def test_retomar_usa_a_tarefa_do_woocommerce(conta):
    """O Retomar mandava toda sincronizacao para a tarefa do Shopify."""
    execucao = _execucao(configuracao(conta))

    caminho, _args, _kwargs = argumentos(execucao)

    assert caminho == "apps.woocommerce.tasks.sincronizar_woocommerce"
