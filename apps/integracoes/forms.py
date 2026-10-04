from django import forms

from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao


def nome_campo(direcao, recurso, operacao):
    return f"{direcao}__{recurso}__{operacao}"


class ConfiguracaoShopifyForm(forms.ModelForm):
    token_acesso = forms.CharField(
        label="Token de acesso",
        required=False,
        widget=forms.PasswordInput(
            render_value=False, attrs={"placeholder": "shpat_..."}
        ),
        help_text="Deixe vazio para manter o token ja salvo.",
    )
    segredo_app = forms.CharField(
        label="Segredo do app (Client secret)",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"placeholder": "Client secret usado para assinar webhooks"},
        ),
        help_text="Usado para validar a assinatura dos webhooks.",
    )
    segredo_avaliacoes = forms.CharField(
        label="Segredo das avaliacoes",
        required=False,
        widget=forms.PasswordInput(
            render_value=False, attrs={"placeholder": "O mesmo de settings.reviews_secret do tema"}
        ),
        help_text=(
            "Crie um texto longo e aleatorio e cole o mesmo nas configuracoes do tema "
            "(reviews_secret). Nao use o segredo do app."
        ),
    )

    class Meta:
        model = ConfiguracaoIntegracao
        fields = ["dominio_loja", "url_webhook", "active"]
        labels = {"active": "Integracao ativa"}
        widgets = {
            "dominio_loja": forms.TextInput(
                attrs={"placeholder": "sua-loja.myshopify.com"}
            ),
            "url_webhook": forms.URLInput(attrs={
                "placeholder": "https://seu-dominio.com/integracoes/shopify/webhook"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.token_criptografado:
            self.fields["token_acesso"].help_text = (
                "Token de acesso já configurado. Preencha novamente somente para substituí-lo."
            )
        if self.instance.segredo_criptografado:
            self.fields["segredo_app"].help_text = (
                "Segredo do app já configurado. Preencha novamente somente para substituí-lo."
            )
        if self.instance.segredo_avaliacoes_criptografado:
            self.fields["segredo_avaliacoes"].help_text = (
                "Segredo das avaliacoes ja configurado. Preencha somente para troca-lo; "
                "troque tambem no tema."
            )
        matriz = permissoes.normalizar(self.instance.permissoes)
        for direcao, _ in permissoes.DIRECOES:
            for recurso, rotulo_recurso in permissoes.RECURSOS:
                for operacao, rotulo_operacao in permissoes.OPERACOES:
                    nome = nome_campo(direcao, recurso, operacao)
                    self.fields[nome] = forms.BooleanField(
                        label=f"{direcao} {rotulo_recurso}: {rotulo_operacao}",
                        required=False,
                        initial=matriz[direcao][recurso][operacao],
                    )

    def clean_dominio_loja(self):
        dominio = self.cleaned_data["dominio_loja"].strip().lower()
        dominio = dominio.removeprefix("https://").removeprefix("http://").strip("/")
        if dominio and ("/" in dominio or not dominio.endswith(".myshopify.com")):
            raise forms.ValidationError("Use o dominio permanente: sua-loja.myshopify.com.")
        return dominio

    def clean(self):
        dados = super().clean()
        if not self.instance.token_criptografado and not dados.get("token_acesso"):
            self.add_error("token_acesso", "Informe o token de acesso do Shopify.")
        return dados

    def save(self, commit=True):
        instancia = super().save(commit=False)
        matriz = permissoes.matriz_vazia()
        for direcao, _ in permissoes.DIRECOES:
            for recurso, _ in permissoes.RECURSOS:
                for operacao, _ in permissoes.OPERACOES:
                    matriz[direcao][recurso][operacao] = bool(
                        self.cleaned_data.get(nome_campo(direcao, recurso, operacao))
                    )
        instancia.permissoes = matriz
        if self.cleaned_data.get("token_acesso"):
            instancia.token_acesso = self.cleaned_data["token_acesso"]
        if self.cleaned_data.get("segredo_app"):
            instancia.segredo_app = self.cleaned_data["segredo_app"]
        if self.cleaned_data.get("segredo_avaliacoes"):
            instancia.segredo_avaliacoes = self.cleaned_data["segredo_avaliacoes"]
        if commit:
            instancia.save()
        return instancia

    def matriz_tela(self):
        linhas = []
        for recurso, rotulo in permissoes.RECURSOS:
            direcoes = []
            for direcao, rotulo_direcao in permissoes.DIRECOES:
                direcoes.append({
                    "nome": direcao,
                    "rotulo": rotulo_direcao,
                    "campos": [self[nome_campo(direcao, recurso, operacao)]
                               for operacao, _ in permissoes.OPERACOES],
                })
            linhas.append({"nome": recurso, "rotulo": rotulo, "direcoes": direcoes})
        return linhas
