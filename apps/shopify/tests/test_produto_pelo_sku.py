"""Produto do Shopify no hub: SKU primeiro, depois o id (vinculo), e so entao cria.

Produto cadastrado no hub (ou pela API do ERP) com o mesmo SKU nao tinha vinculo com
o Shopify: o update era ignorado ("Registro nao encontrado") ou, com Receber > Criar,
virava um produto duplicado.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto
from apps.shopify.webhooks import processar_webhook

pytestmark = pytest.mark.django_db


def _configuracao(conta, criar=True):
    matriz = permissoes.matriz_vazia()
    matriz["receber"]["produtos"]["create"] = criar
    matriz["receber"]["produtos"]["update"] = True
    return ConfiguracaoIntegracao.objects.create(account=conta, plataforma="shopify",
                                                 permissoes=matriz)


def _variante(id_, sku, preco, estoque, posicao):
    return {"id": id_, "title": sku, "sku": sku, "price": preco, "compare_at_price": None,
            "inventory_quantity": estoque, "inventory_policy": "deny", "position": posicao,
            "option1": sku}


def _dados(*variantes):
    return {"id": 10, "title": "Rack Shopify", "handle": "rack-shopify", "body_html": "",
            "options": [{"name": "Cor", "position": 1}], "variants": list(variantes)}


def _rack_do_hub():
    produto = criar_produto("Rack do hub", sku="RACK-BR", price=Decimal("300.00"))
    produto.tipo = Produto.Tipo.VARIAVEL
    produto.save()
    VarianteProduto.objects.create(produto=produto, titulo="Preto", sku="RACK-PT",
                                   price=Decimal("310.00"), posicao=1)
    return produto


def _vinculo_do_produto():
    return ExternalReference.objects.get(platform=Origin.SHOPIFY, entity_type="produtos")


@pytest.mark.parametrize("criar", [True, False])
def test_update_acha_o_produto_pelo_sku_sem_vinculo(conta, criar):
    rack = _rack_do_hub()
    dados = _dados(_variante(101, "RACK-BR", "350.00", 4, 1),
                   _variante(102, "RACK-PT", "360.00", 7, 2))

    mensagem = processar_webhook(_configuracao(conta, criar), "produtos", "update", dados,
                                 lambda *_: None)

    assert mensagem == "Registro atualizado."
    assert Produto.objects.get() == rack
    assert dict(VarianteProduto.objects.values_list("sku", "inventory_quantity")) == {
        "RACK-BR": 4, "RACK-PT": 7}
    assert _vinculo_do_produto().object_id == str(rack.pk)


def test_sku_vale_mais_que_o_vinculo_antigo(conta):
    """Vinculo apontando para outro produto (ex.: importado antes do cadastro certo)."""
    rack = _rack_do_hub()
    outro = criar_produto("Errado", sku="OUTRO-1")
    ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type="produtos",
                                     external_id="gid://shopify/Product/10",
                                     object_id=str(outro.pk))

    processar_webhook(_configuracao(conta), "produtos", "update",
                      _dados(_variante(101, "RACK-PT", "399.00", 1, 1)), lambda *_: None)

    assert VarianteProduto.objects.get(sku="RACK-PT").inventory_quantity == 1
    assert VarianteProduto.objects.get(sku="OUTRO-1").inventory_quantity == 0
    assert _vinculo_do_produto().object_id == str(rack.pk)


def test_variante_pelo_sku_antes_do_vinculo_da_variante(conta):
    """Vinculo de variante trocado: o SKU da loja diz qual variante do hub e."""
    rack = _rack_do_hub()
    branca = VarianteProduto.objects.get(sku="RACK-BR")
    ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type="variantes",
                                     external_id="gid://shopify/ProductVariant/102",
                                     object_id=str(branca.pk))
    ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type="produtos",
                                     external_id="gid://shopify/Product/10",
                                     object_id=str(rack.pk))

    processar_webhook(_configuracao(conta), "produtos", "update",
                      _dados(_variante(101, "RACK-BR", "350.00", 4, 1),
                             _variante(102, "RACK-PT", "360.00", 7, 2)), lambda *_: None)

    assert dict(VarianteProduto.objects.values_list("sku", "inventory_quantity")) == {
        "RACK-BR": 4, "RACK-PT": 7}


def test_sem_sku_e_sem_vinculo_cria(conta):
    processar_webhook(_configuracao(conta), "produtos", "update",
                      _dados(_variante(101, "", "99.00", 2, 1)), lambda *_: None)
    assert Produto.objects.get().nome == "Rack Shopify"


def test_variante_nova_na_loja_entra_no_produto(conta):
    """O update ignorava a variante que a loja criou depois: ela nunca chegava ao hub."""
    rack = _rack_do_hub()

    processar_webhook(_configuracao(conta), "produtos", "update",
                      _dados(_variante(101, "RACK-BR", "350.00", 4, 1),
                             _variante(102, "RACK-PT", "360.00", 7, 2),
                             _variante(103, "RACK-CZ", "370.00", 9, 3)), lambda *_: None)

    assert rack.variantes.get(sku="RACK-CZ").inventory_quantity == 9


def test_sku_repetido_na_loja_nao_gruda_dois_produtos_da_loja_no_mesmo(conta):
    """Produto do SKU ja e de outro produto da loja: e SKU repetido na loja, vale o id."""
    rack = _rack_do_hub()
    outro = criar_produto("Outro do hub", sku="OUTRO-1")
    for externo, obj in (("gid://shopify/Product/9", rack), ("gid://shopify/Product/10", outro)):
        ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type="produtos",
                                         external_id=externo, object_id=str(obj.pk))

    processar_webhook(_configuracao(conta), "produtos", "update",
                      _dados(_variante(101, "RACK-PT", "399.00", 1, 1)), lambda *_: None)

    assert VarianteProduto.objects.get(sku="RACK-PT").inventory_quantity == 0
    assert ExternalReference.objects.get(external_id="gid://shopify/Product/10").object_id == \
        str(outro.pk)
