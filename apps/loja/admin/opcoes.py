"""Opcoes da variante no modal: cada linha e um Tipo (Cor) + um Valor (Branco).

Os tipos e valores sao globais da conta (TipoVariante/ValorVariante); aqui a
variante so escolhe os dela. O select de valor mostra so os do tipo escolhido
(static/starhub/js/selects-dependentes.js, pelo data-pai de cada opcao).
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from apps.core.admin_base import TemaTabularInline
from apps.loja.models import TipoVariante, ValorDaVarianteProduto, ValorVariante


class ValorComTipo(forms.Select):
    """Select de valores com o tipo de cada um em data-pai (o JS filtra por ele)."""

    tipo_de = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcao = super().create_option(name, value, label, selected, index, subindex, attrs)
        pai = self.tipo_de.get(str(getattr(value, "value", value)))
        if pai:
            opcao["attrs"]["data-pai"] = pai
        return opcao


class OpcaoForm(forms.ModelForm):
    tipo = forms.ModelChoiceField(queryset=TipoVariante.objects.none(), label="Tipo")

    class Meta:
        # Pelo Meta o admin usa este select (e ainda o embrulha com o "+").
        widgets = {"valor": ValorComTipo}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoVariante.objects.all()
        campo = self.fields["valor"]
        campo.label_from_instance = lambda valor: valor.valor  # "Branco", nao "Cor: Branco"
        widget = getattr(campo.widget, "widget", campo.widget)  # dentro do "+" do admin
        widget.tipo_de = {
            str(pk): str(tipo) for pk, tipo in ValorVariante.objects.values_list("pk", "tipo_id")
        }
        widget.attrs["data-depende-de"] = "tipo"
        if self.instance.pk:
            self.initial["tipo"] = self.instance.valor.tipo_id

    def clean(self):
        dados = super().clean()
        tipo, valor = dados.get("tipo"), dados.get("valor")
        if tipo and valor and valor.tipo_id != tipo.pk:
            self.add_error("valor", f"{valor.valor} nao e um valor de {tipo.nome}.")
        return dados


class OpcoesFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        vistos = set()
        for form in self.forms:
            dados = getattr(form, "cleaned_data", {})
            if not dados or dados.get("DELETE") or not dados.get("tipo"):
                continue
            if dados["tipo"].pk in vistos:
                # O clean() do model so ve o que ja esta no banco; duas linhas novas nao.
                raise ValidationError(f"A variante tem dois valores de {dados['tipo'].nome}.")
            vistos.add(dados["tipo"].pk)


class OpcoesInline(TemaTabularInline):
    model = ValorDaVarianteProduto
    fk_name = "variante"
    form = OpcaoForm
    formset = OpcoesFormSet
    extra = 0
    fields = ["tipo", "valor"]
    relacao_so_adicionar = ["valor"]
    verbose_name = "opcao"
    verbose_name_plural = "opcoes"
