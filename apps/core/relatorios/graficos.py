"""Mini cards e graficos do relatorio (no padrao do Painel), prontos para o Chart.js.

    indicador("Usos", 3, "wallet")                       -> components/stat_card.html
    grafico("Usos por dia", "barra", ["05/09"], [3])     -> static/starhub/js/relatorio-graficos.js

Dinheiro vai ao JS como texto ("200.00"): o grafico so desenha, quem arredonda e o
servidor. Contagem vai como numero.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from apps.loja.dinheiro import ZERO, texto

# Ate quantos dias o eixo do tempo vai dia a dia; acima disso, mes a mes.
DIAS_NO_EIXO = 62


def indicador(rotulo, valor, icone, tom="primary", detalhe="", eh_moeda=False):
    return {"rotulo": rotulo, "valor": valor, "icone": icone, "tom": tom,
            "detalhe": detalhe, "eh_moeda": eh_moeda}


def grafico(titulo, tipo, rotulos, dados, nome="", moeda=False):
    """tipo: "barra", "linha" ou "rosca"."""
    valores = [texto(v) if moeda else v for v in dados]
    return {"titulo": titulo, "tipo": tipo, "rotulos": list(rotulos), "moeda": moeda,
            "series": [{"nome": nome or titulo, "dados": valores}]}


def _meses(de, ate):
    atual = date(de.year, de.month, 1)
    while atual <= ate:
        yield atual
        atual = date(atual.year + (atual.month == 12), atual.month % 12 + 1, 1)


def eixo_do_tempo(por_dia, de, ate, zero=0):
    """(por "dia" ou "mes", rotulos, valores) com os dias/meses vazios em zero.

    por_dia: {date: valor}. Sem de/ate, o eixo vai do primeiro ao ultimo dado.
    """
    if not por_dia and not (de and ate):
        return "dia", [], []
    inicio = de or min(por_dia)
    fim = ate or max(por_dia)
    if (fim - inicio).days < DIAS_NO_EIXO:
        dias = [inicio + timedelta(days=n) for n in range((fim - inicio).days + 1)]
        return "dia", [d.strftime("%d/%m") for d in dias], [por_dia.get(d, zero) for d in dias]
    por_mes = {}
    for dia, valor in por_dia.items():
        chave = date(dia.year, dia.month, 1)
        por_mes[chave] = por_mes.get(chave, zero) + valor
    meses = list(_meses(inicio, fim))
    return "mes", [m.strftime("%m/%Y") for m in meses], [por_mes.get(m, zero) for m in meses]


def media_por_dia(total, por_dia, de, ate):
    """"0,1": uma casa, virgula, em texto (o card mostra como esta)."""
    if de and ate:
        dias = (ate - de).days + 1
    elif por_dia:
        dias = (max(por_dia) - min(por_dia)).days + 1
    else:
        dias = 1
    media = (Decimal(total) / max(dias, 1)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return str(media).replace(".", ",")


def pico(por_dia):
    """Texto do dia com mais registros: "pico: 2 em 05/09"."""
    if not por_dia:
        return ""
    dia, valor = max(por_dia.items(), key=lambda par: (par[1], -par[0].toordinal()))
    return f"pico: {valor} em {dia.strftime('%d/%m')}"


def somar_dinheiro(valores):
    return sum((v for v in valores if v is not None), ZERO)
