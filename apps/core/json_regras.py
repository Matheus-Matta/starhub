"""Widget das regras de publicacao (PublicationPolicy.rules).

No banco fica o formato do motor de regras (apps/core/services/rules.py):

    {"all": [{"field": "tags", "operator": "contains", "value": "shopify"}], "any": [...]}

Na tela vira uma tabela, uma linha por condicao; a coluna "Grupo" diz se ela
entra em "todas devem valer" (all) ou "basta uma valer" (any).
"""

import json

from django.core.exceptions import ValidationError

from apps.core import json_normalizar
from apps.core.json_widgets import ListaTema
from apps.core.services.rules import validate_rules

GRUPOS = [
    {"valor": "all", "rotulo": "Todas devem valer"},
    {"valor": "any", "rotulo": "Basta uma valer"},
]
OPERADORES = [
    {"valor": "eq", "rotulo": "igual a"},
    {"valor": "neq", "rotulo": "diferente de"},
    {"valor": "gt", "rotulo": "maior que"},
    {"valor": "gte", "rotulo": "maior ou igual a"},
    {"valor": "lt", "rotulo": "menor que"},
    {"valor": "lte", "rotulo": "menor ou igual a"},
    {"valor": "contains", "rotulo": "contem"},
    {"valor": "not_contains", "rotulo": "nao contem"},
    {"valor": "in", "rotulo": "esta na lista"},
    {"valor": "not_in", "rotulo": "nao esta na lista"},
    {"valor": "is_null", "rotulo": "esta vazio"},
    {"valor": "is_not_null", "rotulo": "esta preenchido"},
]
COLUNAS = [
    {"campo": "grupo", "rotulo": "Grupo", "tipo": "escolha", "opcoes": GRUPOS},
    {"campo": "field", "rotulo": "Campo (ex.: tags, metadata.canal)", "tipo": "texto"},
    {"campo": "operator", "rotulo": "Operador", "tipo": "escolha", "opcoes": OPERADORES},
    {"campo": "value", "rotulo": "Valor (10, true, [\"a\", \"b\"])", "tipo": "valor"},
]


def para_linhas(regras):
    """{"all": [...], "any": [...]} -> linhas da tabela, com a coluna grupo."""
    if isinstance(regras, list):  # ja sao linhas (form reexibido depois de erro)
        return regras
    if not isinstance(regras, dict):
        return []
    return [
        {"grupo": grupo, **condicao}
        for grupo in ("all", "any")
        for condicao in regras.get(grupo) or []
        if isinstance(condicao, dict)
    ]


class RegrasTema(ListaTema):
    def __init__(self, attrs=None):
        super().__init__(COLUNAS, com_id=False, botao="Adicionar condicao", attrs=attrs)

    def format_value(self, value):
        try:
            dados = json.loads(value) if isinstance(value, str) else value
        except ValueError:
            return value
        return json.dumps(para_linhas(dados))

    def normalizar(self, valor, rotulo):
        if isinstance(valor, dict):
            validate_rules(valor)
            return valor
        regras = {}
        for linha in json_normalizar.lista(valor, self.colunas, rotulo):
            if not linha["field"]:
                raise ValidationError(f"{rotulo}: toda condicao precisa do campo.")
            regras.setdefault(linha["grupo"], []).append(
                {"field": linha["field"], "operator": linha["operator"], "value": linha["value"]}
            )
        validate_rules(regras)
        return regras
