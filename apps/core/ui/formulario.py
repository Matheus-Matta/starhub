"""Quantas colunas cada campo do change_form ocupa (grade de 2 colunas).

Regra: select, texto, numero, data, tags -> 1 coluna. Imagens, textarea
(descricao) e as tabelas JSON (atributos, endereco, metadados) -> 2 colunas.
O widget pode decidir sozinho com o atributo `largo` (ver json_widgets.py).
"""

from django import forms


def campo_largo(campo_admin):
    bound = getattr(campo_admin, "field", None)  # AdminField.field = BoundField
    widget = getattr(getattr(bound, "field", None), "widget", None)
    if widget is None:
        # Somente leitura: 1 coluna, salvo se o ModelAdmin pedir a linha toda
        # (readonly_largos, ex.: a tabela de variantes do produto).
        nome = bound.get("name") if isinstance(bound, dict) else None
        return nome in getattr(getattr(campo_admin, "model_admin", None), "readonly_largos", ())
    # FK/M2M do admin vem embrulhado (RelatedFieldWidgetWrapper): olha o de dentro.
    widget = getattr(widget, "widget", widget)
    largo = getattr(widget, "largo", None)
    if largo is not None:
        return largo
    return isinstance(widget, forms.Textarea)
