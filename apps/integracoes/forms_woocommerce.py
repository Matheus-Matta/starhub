"""Formulario da conexao com a loja WooCommerce (mesma matriz de permissoes do Shopify).

A chave e o segredo saem de WooCommerce > Configuracoes > Avancado > API REST, com
permissao de leitura e escrita. O segredo tambem assina os webhooks.
"""

from urllib.parse import urlsplit

from django import forms

from apps.integracoes.forms import ConfiguracaoShopifyForm


class ConfiguracaoWooCommerceForm(ConfiguracaoShopifyForm):
    segredo_avaliacoes = None  # avaliacoes pelo tema sao so do Shopify

    token_acesso = forms.CharField(
        label="Chave do consumidor (Consumer key)", required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "ck_..."}),
        help_text="WooCommerce > Configuracoes > Avancado > API REST, com leitura e escrita.",
    )
    segredo_app = forms.CharField(
        label="Segredo do consumidor (Consumer secret)", required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "cs_..."}),
        help_text="Tambem assina os webhooks que a loja manda ao hub.",
    )

    class Meta(ConfiguracaoShopifyForm.Meta):
        fields = [*ConfiguracaoShopifyForm.Meta.fields, "encaminhar_pedidos"]
        widgets = {
            "dominio_loja": forms.URLInput(attrs={"placeholder": "https://sualoja.com.br"}),
            "url_webhook": forms.URLInput(attrs={
                "placeholder": "https://seu-dominio.com/integracoes/woocommerce/webhook"}),
        }
        labels = {"active": "Integracao ativa", "dominio_loja": "Endereco da loja"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.token_criptografado:
            self.fields["token_acesso"].help_text = (
                "Chave ja configurada. Preencha somente para substitui-la.")
        if self.instance.segredo_criptografado:
            self.fields["segredo_app"].help_text = (
                "Segredo ja configurado. Preencha somente para substitui-lo; depois "
                "cadastre os webhooks de novo (eles assinam com o segredo).")

    def clean_dominio_loja(self):
        endereco = self.cleaned_data["dominio_loja"].strip().rstrip("/")
        partes = urlsplit(endereco)
        if endereco and (partes.scheme not in ("http", "https") or not partes.hostname):
            raise forms.ValidationError("Use o endereco completo da loja: https://sualoja.com.br.")
        return endereco

    def clean(self):
        dados = forms.ModelForm.clean(self)
        if not self.instance.token_criptografado and not dados.get("token_acesso"):
            self.add_error("token_acesso", "Informe a chave do consumidor (ck_...).")
        if not self.instance.segredo_criptografado and not dados.get("segredo_app"):
            self.add_error("segredo_app", "Informe o segredo do consumidor (cs_...).")
        return dados
