"""O que fica so no hub e nao vai a marketplace nenhum: registro inativo.

- Pedido desativado (ver pedidos_ativos.py).
- Produto inativo e as variantes dele, inclusive o estoque. O produto que o ERP cria
  pela API Woo nasce assim (woo_api/recursos/produtos_sku.py): so vai para as lojas
  quando o operador ativa, e o primeiro envio cria la.

    fora_das_lojas(produto)   # True: o Distribuidor e a tarefa de envio pulam
"""

from apps.loja.models import Pedido, Produto, VarianteProduto

AVISO_ENVIO = "ignorado: registro inativo no hub (ative para voltar a enviar)"


def fora_das_lojas(obj):
    if isinstance(obj, (Pedido, Produto)):
        return not obj.active
    if isinstance(obj, VarianteProduto):
        return bool(obj.produto_id) and not obj.produto.active
    return False
