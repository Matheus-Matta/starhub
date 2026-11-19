"""Envio ao WooCommerce: variacao e produto achados pelo SKU antes do id (vinculo).

Vinculo velho (variacao/produto apagado e recriado na loja) dava 404 e o preco nunca
chegava; variante sem vinculo com SKU ja na loja era criada de novo ("SKU duplicado").
"""

import pytest

from apps.core.models import ExternalReference
from apps.woocommerce.cliente import WooErro
from apps.woocommerce.importar_produtos import importar_produto
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa
from apps.woocommerce.tests.test_envio import _marketplace

pytestmark = pytest.mark.django_db


def _camiseta(*variacoes):
    produto, _ = importar_produto(exemplos.produto_variavel(), [
        exemplos.variacao(21, "Azul", "CAM-AZ", "49.90", 3),
        exemplos.variacao(22, "Verde", "CAM-VD", "59.90", 1)])
    return produto


def _vinculo_variante(produto, sku):
    return ExternalReference.objects.get(
        platform="woocommerce", entity_type="variantes",
        object_id=str(produto.variantes.get(sku=sku).pk)).external_id


def test_variacao_com_vinculo_velho_vai_para_a_da_loja_com_o_mesmo_sku(conta, monkeypatch):
    """Variacao recriada na loja (id 31): o lote mandava update no 21 e dava 404."""
    loja = LojaFalsa({"products/20/variations": [{"id": 31, "sku": "CAM-AZ"},
                                                 {"id": 22, "sku": "CAM-VD"}]})
    marketplace, loja = _marketplace(conta, monkeypatch, loja)
    produto = _camiseta()

    marketplace.enviar("produtos", "update", produto.pk)

    _, rota, lote = loja.chamadas[-1]
    assert rota == "products/20/variations/batch"
    assert sorted(v["id"] for v in lote["update"]) == [22, 31] and lote["create"] == []
    assert _vinculo_variante(produto, "CAM-AZ") == "31"


def test_variacao_sem_vinculo_que_ja_esta_na_loja_nao_e_criada_de_novo(conta, monkeypatch):
    loja = LojaFalsa({"products/20/variations": [{"id": 21, "sku": "CAM-AZ"},
                                                 {"id": 22, "sku": "CAM-VD"}]})
    marketplace, loja = _marketplace(conta, monkeypatch, loja)
    produto = _camiseta()
    ExternalReference.objects.filter(entity_type="variantes", external_id="22").delete()

    marketplace.enviar("produtos", "update", produto.pk)

    _, _, lote = loja.chamadas[-1]
    assert sorted(v["id"] for v in lote["update"]) == [21, 22] and lote["create"] == []
    assert _vinculo_variante(produto, "CAM-VD") == "22"


def test_estoque_com_vinculo_velho_acha_a_variacao_pelo_sku(conta, monkeypatch):
    class LojaSemA21(LojaFalsa):
        def put(self, caminho, corpo):
            if caminho == "products/20/variations/21":
                self.chamadas.append(("PUT", caminho, corpo))
                raise WooErro("Invalid ID.", 404)
            return super().put(caminho, corpo)

    loja = LojaSemA21({"products": [{"id": 31, "sku": "CAM-AZ", "parent_id": 20}]})
    marketplace, loja = _marketplace(conta, monkeypatch, loja)
    produto = _camiseta()

    marketplace.enviar("estoque", "update", produto.variantes.get(sku="CAM-AZ").pk)

    assert loja.chamadas[-1][:2] == ("PUT", "products/20/variations/31")
    assert _vinculo_variante(produto, "CAM-AZ") == "31"



class LojaSemO15(LojaFalsa):
    def put(self, caminho, corpo):
        if caminho == "products/15":
            self.chamadas.append(("PUT", caminho, corpo))
            raise WooErro("Invalid ID.", 404)
        return super().put(caminho, corpo)


def test_produto_apagado_na_loja_acha_pelo_sku_e_religa(conta, monkeypatch):
    loja = LojaSemO15({"products": [{"id": 40, "sku": "SOFA-1", "parent_id": 0}]})
    marketplace, loja = _marketplace(conta, monkeypatch, loja)
    produto, _ = importar_produto(exemplos.produto_simples())

    marketplace.enviar("produtos", "update", produto.pk)

    assert loja.chamadas[-1][:2] == ("PUT", "products/40")
    assert list(ExternalReference.objects.filter(
        platform="woocommerce", entity_type="produtos", object_id=str(produto.pk)
    ).values_list("external_id", flat=True)) == ["40"]


def test_produto_apagado_sem_sku_na_loja_e_criado_de_novo(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch, LojaSemO15())
    produto, _ = importar_produto(exemplos.produto_simples())

    marketplace.enviar("produtos", "update", produto.pk)

    assert loja.chamadas[-1][:2] == ("POST", "products")
    vinculo = ExternalReference.objects.get(platform="woocommerce", entity_type="produtos",
                                            object_id=str(produto.pk))
    assert vinculo.external_id != "15"
