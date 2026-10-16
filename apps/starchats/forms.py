from django import forms

from apps.starchats.models import ConfiguracaoStarChats


class ConfiguracaoStarChatsForm(forms.ModelForm):
    token_acesso = forms.CharField(
        label="Token de acesso",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Token do perfil no StarChats. Deixe vazio para manter o atual.",
    )
    caixa_entrada_id = forms.TypedChoiceField(
        label="Caixa do WhatsApp oficial",
        required=False,
        coerce=int,
        empty_value=None,
        help_text="A lista vem do StarChats. Ao trocar a caixa, os modelos sao sincronizados.",
    )
    sincronizar_agora = forms.BooleanField(
        label="Buscar caixas e modelos ao salvar",
        required=False,
        help_text="A consulta roda em segundo plano e traz somente caixas de WhatsApp.",
    )

    class Meta:
        model = ConfiguracaoStarChats
        fields = ["url_base", "conta_externa_id", "caixa_entrada_id", "active"]
        labels = {"active": "Integracao ativa"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        caixas = self.instance.caixas_disponiveis or []
        escolhas = [(item["id"], item["nome"]) for item in caixas if item.get("id")]
        atual = self.instance.caixa_entrada_id
        if atual and atual not in {item[0] for item in escolhas}:
            escolhas.append((atual, self.instance.caixa_entrada_nome or f"Caixa {atual}"))
        self.fields["caixa_entrada_id"].choices = [
            ("", "Selecione depois de sincronizar"),
            *escolhas,
        ]
        if self.instance.token_criptografado:
            self.fields["token_acesso"].help_text = (
                "Token ja configurado. Preencha somente para substitui-lo."
            )

    def clean(self):
        dados = super().clean()
        if not self.instance.token_criptografado and not dados.get("token_acesso"):
            self.add_error("token_acesso", "Informe o token de acesso do StarChats.")
        return dados

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if self.cleaned_data.get("token_acesso"):
            instancia.token_acesso = self.cleaned_data["token_acesso"]
        if commit:
            instancia.save()
        return instancia
