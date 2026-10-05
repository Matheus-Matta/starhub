"""Envio do hub para a loja WooCommerce (produtos, variacoes, estoque, pedidos)."""

import pytest

from apps.core.models import ExternalReference
from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.woocommerce.cliente import WooErro
from apps.woocommerce.envio.marketplace import WooCommerceMarketplace
from apps.woocommerce.importar_pedidos import importar_pedido
from apps.woocommerce.importar_produtos import importar_produto
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao

pytestmark = pytest.mark.django_db
ENVIA = tuple((r, o) for r in ("produtos", "estoque", "pedidos", "categorias")
              for o in ("create", "update", "delete"))


def _marketplace(conta, monkeypatch, loja=None):
    loja = (loja or LojaFalsa()).instalar(monkeypatch)
    return WooCommerceMarketplace(configuracao(conta, enviar=ENVIA)), loja


def _produto_do_hub():
    produto, _ = importar_produto(exemplos.produto_simples())
    # Produto nascido no hub: sem o vinculo que a importacao deixou.
    ExternalReference.objects.filter(platform="woocommerce").delete()
    return produto


def test_produto_simples_e_criado_com_preco_em_texto_e_vinculado(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    produto = _produto_do_hub()

    resultado = marketplace.enviar("produtos", "create", produto.pk)

    metodo, rota, corpo = loja.chamadas[-1]
    assert (metodo, rota) == ("POST", "products") and resultado.startswith("criado")
    assert (corpo["sku"], corpo["regular_price"], corpo["stock_quantity"]) == (
        "SOFA-1", "1999.90", 7)
    assert ExternalReference.objects.filter(platform="woocommerce", entity_type="produtos",
                                            object_id=str(produto.pk)).exists()


def test_produto_variavel_manda_as_variacoes_num_lote_e_vincula(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    produto, _ = importar_produto(exemplos.produto_variavel(), [
        exemplos.variacao(21, "Azul", "CAM-AZ", "49.90", 3),
        exemplos.variacao(22, "Verde", "CAM-VD", "59.90", 1)])
    ExternalReference.objects.filter(entity_type="variantes", external_id="22").delete()

    marketplace.enviar("produtos", "update", produto.pk)

    _, rota, lote = loja.chamadas[-1]
    assert rota == "products/20/variations/batch"
    assert [v["id"] for v in lote["update"]] == [21]
    assert lote["create"][0]["attributes"] == [{"name": "Cor", "option": "Verde"}]
    nova = ExternalReference.objects.get(entity_type="variantes",
                                         object_id=str(produto.variantes.get(sku="CAM-VD").pk))
    assert nova.external_parent_id == "20"


def test_variacao_recusada_no_create_nao_perde_o_vinculo_do_produto(conta, monkeypatch):
    """Erro nas variacoes desfazia o vinculo: o reenvio criava o produto de novo na loja."""
    class LojaQueRecusaVariacao(LojaFalsa):
        def post(self, caminho, corpo):
            if caminho.endswith("/batch"):
                return {"create": [{"id": 0, "error": {"message": "SKU duplicado"}}]}
            return super().post(caminho, corpo)

    marketplace, _ = _marketplace(conta, monkeypatch, LojaQueRecusaVariacao())
    produto, _ = importar_produto(exemplos.produto_variavel(), [
        exemplos.variacao(21, "Azul", "CAM-AZ", "49.90", 3)])
    ExternalReference.objects.filter(platform="woocommerce").delete()

    with pytest.raises(WooErro, match="SKU duplicado"):
        marketplace.enviar("produtos", "create", produto.pk)

    assert ExternalReference.objects.filter(entity_type="produtos",
                                            object_id=str(produto.pk)).exists()


def test_estoque_do_produto_simples_vai_no_produto(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    produto, _ = importar_produto(exemplos.produto_simples())

    marketplace.enviar("estoque", "update", produto.variante_padrao.pk)

    assert loja.chamadas[-1] == ("PUT", "products/15",
                                 {"manage_stock": True, "stock_quantity": 7})


def test_estoque_da_variacao_vai_na_rota_da_variacao(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    produto, _ = importar_produto(exemplos.produto_variavel(), [
        exemplos.variacao(21, "Azul", "CAM-AZ", "49.90", 3)])

    marketplace.enviar("estoque", "update", produto.variantes.get().pk)

    assert loja.chamadas[-1][:2] == ("PUT", "products/20/variations/21")


def test_pedido_so_atualiza_status_e_nao_e_criado_pelo_hub(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    importar_produto(exemplos.produto_simples())
    pedido, _ = importar_pedido(exemplos.pedido())
    pedido.status = "completed"
    pedido.save()

    marketplace.enviar("pedidos", "update", pedido.pk)

    _, rota, corpo = loja.chamadas[-1]
    assert rota == "orders/501" and corpo["status"] == "completed"
    assert set(corpo) == {"status", "shipping"}
    ExternalReference.objects.filter(entity_type="pedidos").delete()
    with pytest.raises(EnvioNaoSuportado):
        marketplace.enviar("pedidos", "create", pedido.pk)
