"""Relatorio "Uso de cupons": cada cupom usado num pedido, pela data do pedido.

O pedido guarda o codigo digitado na loja em `linhas_cupom` (formato Woo); o Cupom
do hub e identificado pelo nome, igual a esse codigo. A data de uso e a do pedido na
loja (`placed_at`); pedido sem ela (criado no hub) usa a criacao.

Rascunho e lixeira ficam de fora: nao sao venda. Cancelado e reembolsado entram,
com o status na coluna, porque o cupom foi usado e o operador decide o que contar.
"""

from django.db.models import Q
from django.db.models.functions import Coalesce

from apps.core.relatorios.base import Relatorio, Resultado, Tabela, local, no_periodo
from apps.core.relatorios.graficos import eixo_do_tempo, grafico, indicador, pico
from apps.loja.dinheiro import ValorInvalido, dinheiro, somar
from apps.loja.models import Pedido

FORA = (Pedido.Status.RASCUNHO, Pedido.Status.LIXEIRA)
COLUNAS = ["Data de uso", "Cupom", "Pedido", "Cliente", "E-mail", "Status do pedido",
           "Desconto", "Total do pedido"]
RESUMO = ["Cupom", "Usos", "Desconto total", "Total dos pedidos"]


def _desconto(linha):
    try:
        return dinheiro(linha.get("discount"))
    except ValorInvalido:
        return None  # celula vazia: zero esconderia o dado errado e entraria na soma


def _pedidos(de, ate):
    return (
        Pedido.objects.exclude(status__in=FORA).exclude(linhas_cupom=[])
        .filter(Q(placed_at__isnull=False, **no_periodo("placed_at", de, ate))
                | Q(placed_at__isnull=True, **no_periodo("created_at", de, ate)))
        .select_related("cliente")
        .order_by(Coalesce("placed_at", "created_at"), "pk")
    )


def _usos(pedido):
    for linha in pedido.linhas_cupom or []:
        codigo = str(linha.get("code") or "").strip() if isinstance(linha, dict) else ""
        if codigo:
            yield codigo, _desconto(linha)


def _resumo(linhas):
    # O cliente digita "black10" ou "BLACK10": e o mesmo cupom.
    grupos = {}
    for linha in linhas:
        grupo = grupos.setdefault(linha[1].casefold(), {"cupom": linha[1], "linhas": []})
        grupo["linhas"].append(linha)
    resumo = [
        [g["cupom"], len(g["linhas"]), somar(linha[6] for linha in g["linhas"]),
         somar(linha[7] for linha in g["linhas"])]
        for g in grupos.values()
    ]
    return sorted(resumo, key=lambda linha: (-linha[1], linha[0].casefold()))


class UsoCupons(Relatorio):
    chave = "uso-cupons"
    titulo = "Uso de cupons"
    descricao = "Cada cupom usado em pedido, pela data do pedido na loja, e o total por cupom."
    nome_arquivo = "uso-de-cupons"

    def permitido(self, request):
        return (request.user.has_perm("loja.view_pedido")
                and request.user.has_perm("loja.view_cupom"))

    def gerar(self, request, de, ate, limite, painel=False):
        linhas, totais = [], {}
        for pedido in _pedidos(de, ate):
            for codigo, desconto in _usos(pedido):
                linhas.append([local(pedido.placed_at or pedido.created_at), codigo,
                               pedido.number, str(pedido.cliente or ""), pedido.email,
                               pedido.get_status_display(), desconto, pedido.total])
                # Pelo id: o superusuario ve varias contas, e o numero repete entre elas.
                totais[pedido.pk] = pedido.total
        principal = Tabela("Usos", COLUNAS, linhas[:limite], moeda={6, 7})
        resumo = _resumo(linhas)
        resultado = Resultado(principal, len(linhas), [Tabela("Resumo", RESUMO, resumo,
                                                               moeda={2, 3})])
        if painel:
            resultado.indicadores, resultado.graficos = _painel(linhas, totais, resumo, de, ate)
        return resultado


def _painel(linhas, pedidos, resumo, de, ate):
    """pedidos: {id: total}. Pedido com dois cupons conta uma vez no total vendido."""
    por_dia = {}
    for linha in linhas:
        por_dia[linha[0].date()] = por_dia.get(linha[0].date(), 0) + 1
    cards = [
        indicador("Usos", len(linhas), "wallet", "primary", pico(por_dia)),
        indicador("Desconto total", somar(linha[6] for linha in linhas), "trending-up",
                  "success", "dado pelos cupons no periodo", eh_moeda=True),
        indicador("Total dos pedidos", somar(pedidos.values()), "shopping-cart", "info",
                  f"{len(pedidos)} pedido(s) com cupom", eh_moeda=True),
        indicador("Cupons diferentes", len(resumo), "star", "warning",
                  f"mais usado: {resumo[0][0]}" if resumo else ""),
    ]
    unidade, rotulos, valores = eixo_do_tempo(por_dia, de, ate)
    graficos = [
        grafico(f"Usos por {unidade}", "barra", rotulos, valores, "Usos"),
        grafico("Desconto por cupom", "rosca", [r[0] for r in resumo], [r[2] for r in resumo],
                "Desconto", moeda=True),
        grafico("Usos por cupom", "barra", [r[0] for r in resumo], [r[1] for r in resumo],
                "Usos"),
    ]
    return cards, graficos
