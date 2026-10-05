"""Formulario da conexao com o Suri Shop (mesma matriz de permissoes das outras lojas).

Endpoint e token saem do Portal do Suri > Configuracoes (o endpoint do chatbot,
ex.: https://cbxxxx.azurewebsites.net). O Suri nao assina webhook: nao ha segredo.
"""

from urllib.parse import urlsplit

from django import forms

from apps.integracoes.forms import ConfiguracaoShopifyForm


class ConfiguracaoSuriForm(ConfiguracaoShopifyForm):
    segredo_app = None
    segredo_avaliacoes = None

    token_acesso = forms.CharField(
        label="Token da API", required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "Token do Portal"}),
        help_text="Portal do Suri > Configuracoes, ao lado do endpoint.",
    )

    class Meta(ConfiguracaoShopifyForm.Meta):
        widgets = {
            "dominio_loja": forms.URLInput(attrs={
                "placeholder": "https://cbxxxx.azurewebsites.net"}),
            "url_webhook": forms.URLInput(attrs={
                "placeholder": "https://seu-dominio.com/integracoes/suri/webhook"}),
        }
        labels = {"active": "Integracao ativa", "dominio_loja": "Endpoint do chatbot"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.token_criptografado:
            self.fields["token_acesso"].help_text = (
                "Token ja configurado. Preencha somente para substitui-lo.")

    def clean_dominio_loja(self):
        endereco = self.cleaned_data["dominio_loja"].strip().rstrip("/").removesuffix("/api")
        partes = urlsplit(endereco)
        if endereco and (partes.scheme != "https" or not partes.hostname):
            raise forms.ValidationError(
                "Use o endpoint do chatbot com https, como aparece no Portal do Suri.")
        return endereco

    def clean(self):
        dados = forms.ModelForm.clean(self)
        if not self.instance.token_criptografado and not dados.get("token_acesso"):
            self.add_error("token_acesso", "Informe o token da API do Suri.")
        return dados
