"""Conteudo das linhas de detalhe da listagem (coluna "Acoes"): itens do pedido e
variacoes do produto variavel. Le do prefetch_related do get_queryset de cada
admin: nada de consulta por linha."""

from django.template.loader import render_to_string

from apps.core.admin_utils import acoes_da_linha, badge_status


def _primeira_imagem(*midias):
    return next((m.url for grupo in midias for m in grupo if m.url), "")


def _situacao(variante):
    if variante is None:
        return ""
    return badge_status(variante.stock_status, variante.get_stock_status_display())


def itens_do_pedido(pedido):
    linhas = []
    for item in pedido.itens.all():
        variante, produto = item.variante, item.produto
        linhas.append({
            "item": item,
            "imagem": _primeira_imagem(variante.midias.all() if variante else [],
                                       produto.midias.all() if produto else []),
            "situacao": _situacao(variante),
        })
    conteudo = render_to_string("admin/loja/detalhe_pedido.html", {"linhas": linhas})
    return acoes_da_linha(pedido, conteudo, "Ver itens do pedido")


def variacoes_do_produto(produto):
    linhas = []
    for variante in produto.variantes.all():
        opcoes = sorted(variante.opcoes.all(),
                        key=lambda opcao: (opcao.valor.tipo.posicao, opcao.valor.tipo_id))
        linhas.append({
            "variante": variante,
            "imagem": _primeira_imagem(variante.midias.all()),
            "opcoes": [f"{o.valor.tipo.nome}: {o.valor.valor}" for o in opcoes],
            "situacao": _situacao(variante),
        })
    conteudo = render_to_string("admin/loja/detalhe_variantes.html", {"linhas": linhas})
    return acoes_da_linha(produto, conteudo, "Ver variacoes")
