"""Mini cards e graficos do relatorio generico de um model (modelos.py).

Tudo sai da mesma consulta da lista (conta, periodo, permissao), agrupada no
banco por dia: uma consulta para o eixo do tempo e outra para o status.

- Registros no periodo, media por dia (com o pico) e, se o model tem, ativos;
- coluna em reais na lista (ex.: "total" do pedido): card com a soma e grafico
  do valor por dia;
- primeiro filtro de escolhas da lista (ex.: status): grafico de rosca.
"""

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils.text import capfirst

from apps.core.relatorios.graficos import (
    eixo_do_tempo,
    grafico,
    indicador,
    media_por_dia,
    pico,
    somar_dinheiro,
)
from apps.loja.dinheiro import ZERO, dinheiro


def _campo_de_escolhas(model, filtros):
    nomes = [f for f in filtros if isinstance(f, str)] + ["status"]
    for nome in nomes:
        try:
            campo = model._meta.get_field(nome)
        except FieldDoesNotExist:  # filtro por relacao ("cliente__nome") nao e campo
            continue
        if getattr(campo, "choices", None):
            return campo
    return None


def _por_dia(consulta, campo, dinheiro_campo):
    agregados = {"n": Count("pk")}
    if dinheiro_campo:
        agregados["soma"] = Sum(dinheiro_campo.attname)
    linhas = (consulta.order_by().annotate(dia=TruncDate(campo)).values("dia")
              .annotate(**agregados))
    contagem = {linha["dia"]: linha["n"] for linha in linhas if linha["dia"]}
    somas = {linha["dia"]: dinheiro(linha["soma"]) or ZERO
             for linha in linhas if linha["dia"]} if dinheiro_campo else {}
    return contagem, somas


def _sem_juncoes(consulta):
    """Os mesmos registros da lista, sem as anotacoes do admin. A lista de pedidos junta
    os itens (coluna "itens"): agrupar por cima dela contava e somava cada pedido uma
    vez por item. O filtro por pk mantem conta, periodo e permissao da lista."""
    return consulta.model._base_manager.filter(pk__in=consulta.order_by().values("pk"))


def montar(consulta, total, campo_data, filtros, dinheiro_campo, de, ate):
    """(indicadores, graficos) do periodo."""
    model = consulta.model
    consulta = _sem_juncoes(consulta)
    contagem, somas = _por_dia(consulta, campo_data, dinheiro_campo) if campo_data else ({}, {})
    cards = [
        indicador("Registros no periodo", total, "chart-column", "primary",
                  "criados entre as datas escolhidas"),
        indicador("Media por dia", media_por_dia(total, contagem, de, ate), "trending-up",
                  "info", pico(contagem)),
    ]
    graficos = []
    if campo_data:
        unidade, rotulos, valores = eixo_do_tempo(contagem, de, ate)
        graficos.append(grafico(f"Novos por {unidade}", "barra", rotulos, valores, "Registros"))
    if dinheiro_campo:
        nome = dinheiro_campo.verbose_name
        cards.append(indicador(f"Soma de {nome}", somar_dinheiro(somas.values()), "wallet",
                               "success", f"{nome} dos registros do periodo", eh_moeda=True))
        unidade, rotulos, valores = eixo_do_tempo(somas, de, ate, ZERO)
        graficos.append(grafico(f"{capfirst(nome)} por {unidade}", "linha", rotulos, valores,
                                capfirst(nome), moeda=True))
    if any(campo.name == "active" for campo in model._meta.concrete_fields):
        ativos = consulta.filter(active=True).count()
        cards.append(indicador("Ativos", ativos, "circle-check", "warning",
                               f"{total - ativos} inativos"))
    escolhas = _campo_de_escolhas(model, filtros)
    if escolhas:
        nomes = dict(escolhas.flatchoices)
        contas = (consulta.order_by().values(escolhas.attname).annotate(n=Count("pk"))
                  .order_by("-n"))
        graficos.append(grafico(
            f"Por {escolhas.verbose_name}", "rosca",
            [str(nomes.get(linha[escolhas.attname], linha[escolhas.attname] or "-"))
             for linha in contas],
            [linha["n"] for linha in contas], capfirst(escolhas.verbose_name)))
    return cards[:4], graficos
