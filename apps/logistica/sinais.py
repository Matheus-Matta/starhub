"""Sinal "as tabelas de frete mudaram em lote" (importacao de planilha).

A importacao grava faixa por faixa sem avisar (origem "importacao"); no fim manda este
sinal uma vez. Quem leva o frete para uma loja (ex.: apps/woocommerce/frete_sinais.py)
reenvia uma vez so, em vez de uma por linha da planilha.
"""

from django.dispatch import Signal

tabelas_alteradas = Signal()
