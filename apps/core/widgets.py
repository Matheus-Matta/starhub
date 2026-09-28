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
FORMATO_HORA = "%H:%M"
ATTRS_DATA = {"data-calendario": "", "placeholder": "dd/mm/aaaa", "autocomplete": "off"}


class DataTema(forms.DateInput):
    def __init__(self, attrs=None):
        super().__init__(attrs={**ATTRS_DATA, **(attrs or {})}, format=FORMATO_DATA)


class DataHoraTema(forms.SplitDateTimeWidget):
    """Data (com calendario) + hora (input time do navegador), lado a lado.
    Mesmo contrato do AdminSplitDateTime: o form continua SplitDateTimeField."""

    template_name = "core/widgets/data_hora.html"

    def __init__(self, attrs=None):
        super().__init__(
            attrs=attrs,
            date_format=FORMATO_DATA,
            time_format=FORMATO_HORA,
            date_attrs=dict(ATTRS_DATA),
            time_attrs={"type": "time"},
        )


class SwitchTema(forms.CheckboxInput):
    """Checkbox desenhado como switch (classe .switch em checkbox-switch.css)."""

    def __init__(self, attrs=None):
        base = {"class": "switch", "role": "switch"}
        super().__init__(attrs={**base, **(attrs or {})})


def ligar_periodo(widget, campo_fim):
    """Faz o calendario do campo inicial abrir em modo periodo e preencher
    tambem `campo_fim` (ex.: promocao_inicio -> promocao_fim)."""
    alvo = widget.widgets[0] if isinstance(widget, forms.MultiWidget) else widget
    alvo.attrs["data-periodo-fim"] = campo_fim
    return widget
