"""A mutacao de atualizar produto precisa ser aceita pelo Shopify."""

import re

from apps.shopify.envio import produtos


def test_atualizar_produto_nao_pede_last_sem_before():
    """O Shopify respondia "using last without before is not supported" e todo
    produtos update falhava (o preco do ERP nao chegava a loja)."""
    for consulta in (produtos.ATUALIZAR, produtos.CRIAR):
        for argumentos in re.findall(r"\(([^)]*last:[^)]*)\)", consulta):
            assert "before:" in argumentos, consulta
