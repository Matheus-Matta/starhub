"""Atualiza somente registros ja vinculados ao Shopify."""

from apps.shopify import categorias_imagem, produtos_dados
from apps.shopify.cupons import atualizar_desconto
from apps.shopify.imagens import sincronizar_imagens
from apps.shopify.pedidos import importar_pedido
from apps.shopify.pedidos_base import ids_do_pedido
from apps.shopify.produtos import atualizar_variantes
from apps.shopify.recursos import _decimal, _existente, estoque


def produto(dados):
    obj = _existente("produtos", dados["id"])
    if obj is None:
        return None, False
    atualizar_variantes(obj, dados, _decimal)
    produtos_dados.aplicar(obj, dados)
    sincronizar_imagens(obj, dados)
    return obj, True


def categoria(dados):
    obj = _existente("categorias", dados["id"])
    if obj is None:
        return None, False
    obj.nome = dados.get("title") or obj.nome
    obj.descricao = dados.get("descriptionHtml") or ""
    obj.imagem = categorias_imagem.recebida(obj, dados.get("image"))
    obj.save()
    return obj, True


def cliente(dados):
    from apps.shopify.clientes import atualizar_cliente

    return atualizar_cliente(dados)


def pedido(dados):
    externo, _numero = ids_do_pedido(dados)
    if _existente("pedidos", externo) is None:
        return None, False
    obj, _criado = importar_pedido(dados)
    return obj, True


def cupom(dados):
    obj = _existente("cupons", dados["id"])
    if obj is None:
        return None, False
    return atualizar_desconto(obj, dados), True


def atualizar_estoque(dados):
    obj, _ = estoque(dados)
    return obj, obj is not None


ATUALIZADORES = {
    "produtos": produto,
    "categorias": categoria,
    "clientes": cliente,
    "pedidos": pedido,
    "cupons": cupom,
    "estoque": atualizar_estoque,
}
