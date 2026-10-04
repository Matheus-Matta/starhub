"""Um item com erro na importacao e pulado e registrado; o resto da sync segue."""

import pytest
from django.db import IntegrityError

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Produto
from apps.shopify import recursos, sincronizar
from apps.shopify.cliente import ShopifyErro
from apps.shopify.tasks import sincronizar_shopify
from apps.shopify.tests.test_produto_completo import node
from apps.shopify.tests.test_sincronizar import _configuracao


def _produto(numero, **extra):
    sufixo = {"id": f"gid://shopify/Product/{numero}", "handle": f"p-{numero}",
              "title": f"Produto {numero}"}
    variantes = {"nodes": [{"id": f"gid://shopify/ProductVariant/{numero}",
                            "sku": f"SKU-{numero}", "price": "10.00"}]}
    return node(**sufixo, variants=variantes, **extra)


def _rodar(monkeypatch, itens):
    config = _configuracao(("produtos", "get"))
    config.save()

    class Cliente:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return None

        def listar(self, _recurso):
            for dado in itens:
                if isinstance(dado, Exception):
                    raise dado
                yield dado

    monkeypatch.setattr(sincronizar, "ShopifyClient", Cliente)
    monkeypatch.setitem(sincronizar.CONVERSORES, "produtos", lambda dados: dados)
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=ConfiguracaoIntegracao.objects.get(pk=config.pk),
        tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR)
    sincronizar_shopify.run(str(execucao.pk))
    execucao.refresh_from_db()
    return execucao


@pytest.mark.django_db
def test_item_com_erro_e_pulado_e_os_outros_entram(monkeypatch):
    """Antes um produto quebrado derrubava a sync e os seguintes nem eram lidos."""
    aplicar = recursos.produtos_dados.aplicar

    def quebra_o_2(produto, dados, sobrescrever=False):
        if dados["id"].endswith("/2"):
            raise IntegrityError("duplicate key")
        return aplicar(produto, dados, sobrescrever)

    monkeypatch.setattr(recursos.produtos_dados, "aplicar", quebra_o_2)

    execucao = _rodar(monkeypatch, [_produto(1), _produto(2), _produto(3)])

    assert sorted(Produto.objects.values_list("slug", flat=True)) == ["p-1", "p-3"]
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
    assert len(execucao.falhas) == 1
    falha = execucao.falhas[0]
    assert falha["recurso"] == "produtos"
    assert falha["id_externo"] == "gid://shopify/Product/2"
    assert falha["descricao"] == "Produto 2"
    assert "mesmo codigo" in falha["motivo"]
    assert not Produto.objects.filter(slug="p-2").exists(), "savepoint desfaz o item"


@pytest.mark.django_db
def test_erro_de_autenticacao_continua_derrubando_a_sync(monkeypatch):
    """Credencial recusada afeta todos os itens: pular so geraria milhares de falhas."""
    execucao = _rodar(monkeypatch, [
        _produto(1), ShopifyErro("Shopify respondeu HTTP 401: Unauthorized")])

    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert ExternalReference.objects.filter(entity_type="produtos").count() == 1
