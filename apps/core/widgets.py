"""Widgets de formulario do tema. O HTML continua o do Django; o que muda sao
atributos que o JS do tema (static/starhub/js/datas.js) le para montar o
calendario. Select, multi-select, checkbox e switch nao precisam de widget:
o JS e o CSS pegam os campos padrao sozinhos.

Exemplo num form comum:
    class FiltroForm(forms.Form):
        inicio = forms.DateField(widget=DataTema())
        ativo = forms.BooleanField(widget=SwitchTema(), required=False)
"""

from django import forms

FORMATO_DATA = "%d/%m/%Y"
FORMATO_DATA_HORA = "%Y-%m-%dT%H:%M"
ATTRS_DATA = {"data-calendario": "", "placeholder": "dd/mm/aaaa", "autocomplete": "off"}


class DataTema(forms.DateInput):
    def __init__(self, attrs=None):
        super().__init__(attrs={**ATTRS_DATA, **(attrs or {})}, format=FORMATO_DATA)


class DataHoraTema(forms.DateTimeInput):
    """Data e horario juntos, no controle nativo datetime-local do navegador."""

    input_type = "datetime-local"

    def __init__(self, attrs=None):
        base = {"autocomplete": "off"}
        super().__init__(attrs={**base, **(attrs or {})}, format=FORMATO_DATA_HORA)


class SwitchTema(forms.CheckboxInput):
    """Checkbox desenhado como switch (classe .switch em checkbox-switch.css)."""

    def __init__(self, attrs=None):
        base = {"class": "switch", "role": "switch"}
        super().__init__(attrs={**base, **(attrs or {})})


class EditorHTML(forms.Textarea):
    """Textarea progressivo que o JavaScript transforma em editor visual de HTML."""

    def __init__(self, attrs=None):
        base = {"data-editor-html": "", "rows": 10}
        super().__init__(attrs={**base, **(attrs or {})})

    class Media:
        css = {"all": ("starhub/css/editor-html.css",)}
        js = ("starhub/js/editor-html.js",)


def ligar_periodo(widget, campo_fim):
    """Faz o calendario do campo inicial abrir em modo periodo e preencher
    tambem `campo_fim` (ex.: promocao_inicio -> promocao_fim)."""
    alvo = widget.widgets[0] if isinstance(widget, forms.MultiWidget) else widget
    alvo.attrs["data-periodo-fim"] = campo_fim
    return widget
