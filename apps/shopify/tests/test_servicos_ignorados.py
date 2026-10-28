"""Servico marcado "nao enviar as lojas": nem o tema nem o produto escondido o oferecem."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.loja.models import Servico
from apps.loja.services.extras_pedido import extras
from apps.shopify.contexto import usando_configuracao
from apps.shopify.pedidos import importar_pedido
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401
from apps.shopify.tests.test_servicos_shopify import (  # noqa: F401
    ORIGEM,
    _exportar,
    _sem_rede,
    cfg,
    montagem,
    sofa,
)

pytestmark = pytest.mark.django_db


def test_servico_ignorado_na_shopify_some_do_bloco_do_tema(client, cfg, sofa, montagem):  # noqa: F811
    _exportar(cfg, montagem)
    montagem.fora_das_integracoes = ["shopify"]
    montagem.save()

    resposta = client.get(reverse("shopify_servicos_publico", args=[cfg.uuid]),
                          {"produto": "111"}, headers={"Origin": ORIGEM})

    assert resposta.json() == {"servicos": []}


def test_servico_ignorado_na_shopify_vira_rascunho_na_shopify(cfg, montagem):  # noqa: F811
    montagem.fora_das_integracoes = ["shopify"]
    montagem.save()

    entrada = _exportar(cfg, montagem).chamadas[0][1]["input"]

    assert entrada["status"] == "DRAFT"


@pytest.mark.usefixtures("produto_shopify_falso")
def test_pedido_da_shopify_ganha_o_servico_automatico(cfg, sofa):  # noqa: F811
    """O cliente nao marcou a montagem gratis; o pedido chega com ela no item."""
    gratis = Servico.objects.create(nome="Montagem gratis", sku="8875", preco=Decimal("0"),
                                    inclusao=Servico.Inclusao.TODOS, fora_das_integracoes=["suri"])
    linha = {"id": 901, "title": "Sofa", "sku": "SOF-1", "product_id": 111,
             "variant_id": 9001, "quantity": 1, "price": "1500.00",
             "discount_allocations": [], "tax_lines": []}

    with usando_configuracao(cfg):
        pedido, _ = importar_pedido(pedido_shopify(
            discount_codes=[], discount_applications=[], line_items=[linha]))

    servico = next(s for s in extras(pedido)["servicos"] if s["servico_id"] == gratis.pk)
    assert servico["item_id"] == pedido.itens.get().pk and servico["preco"] == "0.00"
