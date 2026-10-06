"""Formularios do SMTP e da configuracao de notificacao.

A configuracao de notificacao ganha um switch por evento e canal ("pedido_criado__email"),
montado do catalogo (eventos.py): evento novo no catalogo aparece sozinho na tela.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.notificacoes import email, eventos
from apps.notificacoes.models import ConfiguracaoEmail, ConfiguracaoNotificacao


class ConfiguracaoEmailForm(forms.ModelForm):
    senha = forms.CharField(label="Senha", required=False,
                            widget=forms.PasswordInput(render_value=False),
                            help_text="Deixe vazio para manter a senha ja salva.")
    testar = forms.BooleanField(
        label="Enviar e-mail de teste ao salvar", required=False,
        help_text="Vai para o seu e-mail; o resultado chega no sino do cabecalho.")

    class Meta:
        model = ConfiguracaoEmail
        fields = ["host", "porta", "seguranca", "usuario", "remetente_email", "remetente_nome"]

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if self.cleaned_data.get("senha"):
            instancia.senha = self.cleaned_data["senha"]
        if commit:
            instancia.save()
        return instancia


def nome_campo(evento, canal):
    return f"{evento.replace('.', '_')}__{canal}"


def linhas():
    """[(grupo, [(campo navegador, campo e-mail)])] para os fieldsets do admin."""
    return [(grupo, [tuple(nome_campo(evento, canal) for canal, _ in eventos.CANAIS)
                     for evento, _ in itens])
            for grupo, itens in eventos.catalogo()]


class _RegrasBase(forms.ModelForm):
    class Meta:
        model = ConfiguracaoNotificacao
        fields = ["ligado", "destinatarios"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        regras = self.instance.regras or {}
        for evento in eventos.EVENTOS:
            for canal, _ in eventos.CANAIS:
                self.fields[nome_campo(evento, canal)].initial = bool(
                    regras.get(evento, {}).get(canal))

    def clean_destinatarios(self):
        """Cada e-mail alvo valido; volta um por linha, ja limpo."""
        enderecos = email.destinatarios(self.cleaned_data.get("destinatarios"))
        invalidos = []
        for endereco in enderecos:
            try:
                validate_email(endereco)
            except ValidationError:
                invalidos.append(endereco)
        if invalidos:
            raise ValidationError(f"E-mail invalido: {', '.join(invalidos)}. Confira e salve.")
        return "\n".join(enderecos)

    def clean(self):
        dados = super().clean()
        com_email = any(dados.get(nome_campo(evento, "email")) for evento in eventos.EVENTOS)
        if com_email and not dados.get("destinatarios") and "destinatarios" not in self.errors:
            self.add_error("destinatarios", "Cadastre ao menos um e-mail alvo: e para ele que "
                                            "vao os e-mails das notificacoes ligadas.")
        return dados

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.regras = {
            evento: {canal: bool(self.cleaned_data.get(nome_campo(evento, canal)))
                     for canal, _ in eventos.CANAIS}
            for evento in sorted(eventos.EVENTOS)}
        if commit:
            instancia.save()
        return instancia


def _campos():
    campos = {}
    for _grupo, itens in eventos.catalogo():
        for evento, rotulo in itens:
            for canal, nome_canal in eventos.CANAIS:
                campos[nome_campo(evento, canal)] = forms.BooleanField(
                    label=f"{rotulo}: {nome_canal.lower()}", required=False)
    return campos


# Os campos sao declarados na classe: o admin so aceita nos fieldsets campo que o form tem.
ConfiguracaoNotificacaoForm = type("ConfiguracaoNotificacaoForm", (_RegrasBase,), _campos())
