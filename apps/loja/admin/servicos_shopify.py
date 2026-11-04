from django import forms
from django.core.exceptions import ValidationError

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Servico
from apps.shopify.models import ApresentacaoServicoShopify

Apresentacao = ApresentacaoServicoShopify
CAMPO_LAYOUT = "shopify_tipo_campo"
CAMPOS_LAYOUT = (
    CAMPO_LAYOUT, "shopify_rotulo", "shopify_descricao", "shopify_ordem",
    "shopify_servicos_vinculados", "shopify_titulo_grupo", "shopify_obrigatorio",
    "shopify_padrao",
)


class ServicoShopifyForm(forms.ModelForm):
    shopify_tipo_campo = forms.ChoiceField(
        label="Tipo do campo", choices=Apresentacao.TipoCampo.choices,
        required=False, initial=Apresentacao.TipoCampo.CHECKBOX)
    shopify_rotulo = forms.CharField(
        label="Rotulo", required=False,
        help_text="Vazio usa o nome do servico.",
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Montagem profissional"}))
    shopify_descricao = forms.CharField(
        label="Descricao", required=False,
        help_text="Texto curto mostrado abaixo da opcao.",
        widget=forms.Textarea(attrs={"placeholder": "Ex.: Realizada em ate 2 dias", "rows": 2}))
    shopify_ordem = forms.IntegerField(
        label="Ordem", min_value=0, initial=10, required=False,
        help_text="Menor aparece primeiro.",
        widget=forms.NumberInput(attrs={"placeholder": "10"}))
    shopify_servicos_vinculados = forms.ModelMultipleChoiceField(
        label="Servicos vinculados", queryset=Servico.objects.none(), required=False,
        help_text="No Radio, Lista ou Cartoes, escolha todas as alternativas do grupo.")
    shopify_titulo_grupo = forms.CharField(
        label="Titulo do grupo", required=False,
        help_text="Exemplo: Escolha o tipo de garantia.",
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Escolha uma protecao"}))
    shopify_obrigatorio = forms.BooleanField(
        label="Escolha obrigatoria", required=False)
    shopify_padrao = forms.ChoiceField(
        label="Opcao inicial", choices=Apresentacao.Padrao.choices,
        required=False, initial=Apresentacao.Padrao.NENHUM)

    class Meta:
        model = Servico
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if CAMPO_LAYOUT not in self.fields:
            return
        self.fields["shopify_servicos_vinculados"].queryset = (
            Servico.objects.exclude(pk=self.instance.pk).order_by("nome"))
        self._apresentacao = (
            Apresentacao.objects.filter(servico=self.instance).first()
            if self.instance.pk else None)
        if self._apresentacao:
            for nome in CAMPOS_LAYOUT:
                atributo = nome.removeprefix("shopify_")
                self.initial[nome] = (
                    self._apresentacao.servicos_vinculados.all()
                    if atributo == "servicos_vinculados"
                    else getattr(self._apresentacao, atributo))

    def clean(self):
        dados = super().clean()
        if CAMPO_LAYOUT not in self.fields:
            return dados
        dados[CAMPO_LAYOUT] = dados.get(CAMPO_LAYOUT) or Apresentacao.TipoCampo.CHECKBOX
        dados["shopify_padrao"] = dados.get("shopify_padrao") or Apresentacao.Padrao.NENHUM
        if dados.get("shopify_ordem") is None:
            dados["shopify_ordem"] = 10
        apresentacao = self._apresentacao or Apresentacao(
            servico=self.instance, account_id=self.instance.account_id)
        for nome in CAMPOS_LAYOUT:
            if nome in dados and nome != "shopify_servicos_vinculados":
                setattr(apresentacao, nome.removeprefix("shopify_"), dados[nome])
        try:
            apresentacao.validar_vinculados(dados.get("shopify_servicos_vinculados") or [])
        except ValidationError as erro:
            for nome, erros in erro.error_dict.items():
                destino = f"shopify_{nome}"
                for item in erros:
                    self.add_error(destino if destino in self.fields else None, item)
        self._apresentacao = apresentacao
        return dados

    def salvar_apresentacao(self):
        apresentacao = self._apresentacao
        apresentacao.servico = self.instance
        apresentacao.account_id = self.instance.account_id
        apresentacao.save()
        apresentacao.servicos_vinculados.set(
            self.cleaned_data.get("shopify_servicos_vinculados") or [])


class LayoutServicoShopifyMixin:
    form = ServicoShopifyForm

    def _shopify_configurado(self):
        return ConfiguracaoIntegracao.objects.filter(
            plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
            active=True,
        ).exclude(dominio_loja="").exists()

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        if self._shopify_configurado():
            return form

        class FormSemLayoutShopify(form):
            pass

        FormSemLayoutShopify.base_fields = form.base_fields.copy()
        for nome in CAMPOS_LAYOUT:
            FormSemLayoutShopify.base_fields.pop(nome, None)
        return FormSemLayoutShopify

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if self._shopify_configurado():
            fieldsets.append(("Layout na Shopify", {
                "fields": [
                    ("shopify_tipo_campo", "shopify_ordem"),
                    ("shopify_rotulo", "shopify_descricao"),
                    ("shopify_servicos_vinculados", "shopify_titulo_grupo"),
                    ("shopify_obrigatorio", "shopify_padrao"),
                ],
                "description": "Radio, Lista e Cartoes podem reunir varias alternativas. "
                               "So aparecem no grupo os servicos disponiveis no produto.",
            }))
        return fieldsets

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if CAMPO_LAYOUT in form.fields:
            form.salvar_apresentacao()
