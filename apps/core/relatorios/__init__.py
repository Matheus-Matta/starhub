"""Relatorios do admin (menu "Relatorios"): um por model do tema e os especiais.

    base.py       Tabela, Resultado e a classe Relatorio
    modelos.py    relatorio generico de um ModelAdmin (colunas da lista)
    registro.py   quais relatorios existem e quais a pessoa pode ver
    exportar.py   Excel (openpyxl) e PDF (reportlab)
    views.py      a pagina e o download

Relatorio especial (ex.: apps/loja/relatorios.py, uso de cupons) entra em
settings.STARHUB_RELATORIOS.
"""
