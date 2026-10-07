"""O JSON de docs/pedido-json-erp.md e o que a API devolve de verdade.

O pedido Shopify de exemplo passa pelo webhook (servicos nas propriedades do item,
agendamento nos note_attributes) e e lido em GET /wp-json/wc/v3/orders/<id>. So o
que muda a cada execucao (ids do banco, chave aleatoria, data de alteracao) e
trocado por valores fixos. Se este teste falha depois de mudar a API, rode

    ATUALIZAR_EXEMPLOS=1 python -m pytest apps/woo_api/tests/test_doc_pedido_json.py

e confira o diff do JSON e do texto do documento.
"""

import json
import os
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401
from apps.shopify.webhooks import processar_webhook

pytestmark = pytest.mark.usefixtures("produto_shopify_falso")
RAIZ = Path(__file__).resolve().parents[3]
JSON_DOC = RAIZ / "docs" / "exemplos" / "pedido-completo.json"
MD_DOC = RAIZ / "docs" / "pedido-json-erp.md"
INICIO = "<!-- pedido-completo:inicio -->\n```json\n"
FIM = "\n```\n<!-- pedido-completo:fim -->"
BLOCO = re.compile(re.escape(INICIO) + "(.*?)" + re.escape(FIM), re.S)


def _pedido_da_loja():
    dados = pedido_shopify()
    poltrona = dados["line_items"][0]
    poltrona["properties"] = [
        {"name": "_impermeabilizacao_123", "value": "Sim [+ R$ 499,99]"},
        {"name": "_montagem_456", "value": "Sim [+ R$ 120,00]"},
        {"name": "_garantia_789", "value": "Não"},
    ]
    return dados


def _fixar(corpo):
    """Ids do banco por ordem de aparecimento (1, 2...), chave e data fixas."""
    produtos, servicos = {}, {}

    def produto(pk):
        return produtos.setdefault(pk, len(produtos) + 1) if pk else 0

    corpo.update(id=1, number="1", customer_id=1, order_key="wc_order_a1b2c3d4e5f60",
                 date_modified="2026-09-30T15:00:05", date_modified_gmt="2026-09-30T18:00:05")
    for posicao, linha in enumerate(corpo["line_items"], start=1):
        linha["id"], linha["product_id"] = posicao, produto(linha["product_id"])
        for meta in linha["meta_data"]:
            if meta["key"] == "starhub":
                for servico in meta["value"]["servicos"]:
                    servico["id"] = servicos.setdefault(servico["id"], len(servicos) + 1)
            elif meta["key"].startswith("epofw_field_"):
                valor = json.loads(meta["value"])
                valor[meta["key"]]["product_id"] = str(linha["product_id"])
                meta["value"] = json.dumps(valor, ensure_ascii=False)
    return corpo


def test_json_do_documento_e_o_que_a_api_devolve(api, conta):
    ConfiguracaoIntegracao.objects.create(nome="Shopify", dominio_loja="loja.myshopify.com",
                                          id_vendedor=12)
    criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))
    processar_webhook(None, "pedidos", "create", _pedido_da_loja(), lambda *_: None)
    pedido = Pedido.objects.get()

    gerado = json.dumps(_fixar(api.get(f"/wp-json/wc/v3/orders/{pedido.pk}").json()),
                        ensure_ascii=False, indent=2)

    if os.environ.get("ATUALIZAR_EXEMPLOS"):
        JSON_DOC.write_text(gerado + "\n", encoding="utf-8")
        texto = MD_DOC.read_text(encoding="utf-8")
        MD_DOC.write_text(BLOCO.sub(lambda _: INICIO + gerado + FIM, texto), encoding="utf-8")
    assert JSON_DOC.read_text(encoding="utf-8").strip() == gerado
    assert BLOCO.search(MD_DOC.read_text(encoding="utf-8")).group(1) == gerado
