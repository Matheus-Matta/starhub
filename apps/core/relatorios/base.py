"""Contrato de um relatorio: titulo, permissao e as tabelas de um periodo."""

from dataclasses import dataclass, field
from datetime import date, datetime

from django.utils import timezone


@dataclass
class Tabela:
    titulo: str
    colunas: list
    # Celulas tipadas (Decimal, int, date, datetime sem fuso, str): o Excel
    # recebe numero e data de verdade; o PDF e a tela formatam.
    linhas: list = field(default_factory=list)
    # Indices das colunas em reais. Decimal fora daqui (peso, medida) nao ganha "R$".
    moeda: set = field(default_factory=set)


@dataclass
class Resultado:
    principal: Tabela
    total: int  # linhas do periodo; `principal.linhas` pode vir cortada no limite
    resumos: list = field(default_factory=list)
    # Topo da pagina, no padrao do Painel (graficos.py): mini cards e graficos.
    indicadores: list = field(default_factory=list)
    graficos: list = field(default_factory=list)


class Relatorio:
    chave = ""
    titulo = ""
    descricao = ""
    # Nome da aba/arquivo: so letras simples, o Excel recusa ":" "/" e afins.
    nome_arquivo = "relatorio"

    def permitido(self, request):
        raise NotImplementedError

    def gerar(self, request, de, ate, limite):
        """Resultado do periodo [de, ate] (datas, inclusive; None = sem ponta)."""
        raise NotImplementedError


def local(valor):
    """datetime com fuso -> hora da loja sem fuso (o openpyxl recusa fuso)."""
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.replace(tzinfo=None, microsecond=0)
    return valor


def no_periodo(campo, de, ate):
    """Filtro Django de [de, ate] pela DATA na hora da loja: "ate 30/09" inclui o dia 30."""
    filtros = {}
    if de:
        filtros[f"{campo}__date__gte"] = de
    if ate:
        filtros[f"{campo}__date__lte"] = ate
    return filtros


def dentro(valor, de, ate):
    dia = local(valor).date() if isinstance(valor, datetime) else valor
    if not isinstance(dia, date):
        return False
    return (not de or dia >= de) and (not ate or dia <= ate)
