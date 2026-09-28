"""Enderecos de cobranca e entrega no admin de cliente e de pedido.

O endereco vive em core.Address, mas na tela cada parte e um campo de verdade
do formulario (cobranca_postcode, cobranca_number...): entra na mesma grade de 12
colunas do resto ("CEP | Endereco | Numero" = 3 + 7 + 2), com placeholder,
mascara e validacao por campo. As chaves sao as do Woo (campos.ENDERECO), que e
o formato que a API devolve ao ERP. O que o ERP mandou a mais (persontype, rg...)
aparece em "Outros campos" e continua salvo.

    fieldsets = [..., secao_endereco("cobranca", "Endereco de cobranca"), ...]
"""

from django import forms
from django.core.exceptions import ValidationError

from apps.core.json_widgets import CampoJSON, ObjetoTema
from apps.core.models import Address
from apps.core.validators import validar_cnpj, validar_cpf, validar_telefone
from apps.loja.admin import campos
from apps.loja.services import enderecos

# prefixo dos campos -> (tipo do Woo, definicao dos campos)
TIPOS = {"cobranca": ("billing", campos.COBRANCA), "entrega": ("shipping", campos.ENDERECO)}
VALIDADORES = {"cpf": validar_cpf, "cnpj": validar_cnpj, "phone": validar_telefone}
# Erro do Address.clean() -> campo da tela. Telefone e documento ja tem validador proprio.
ERRO_PARA_CHAVE = {"postal_code": "postcode", "state_code": "state", "country_code": "country"}
OUTROS = "outros"


def _campo(definicao):
    attrs = {"placeholder": definicao.get("placeholder", "")}
    if definicao.get("mascara"):
        attrs["data-mascara"] = definicao["mascara"]
        if definicao["mascara"] not in ("uf", "pais"):
            attrs["inputmode"] = "numeric"
    validador = VALIDADORES.get(definicao["campo"])
    campo = forms.CharField(
        label=definicao["rotulo"], required=False, max_length=200,
        widget=forms.TextInput(attrs=attrs), validators=[validador] if validador else [],
    )
    campo.colunas = definicao.get("largura")  # fieldset.html -> celula-cN
    return campo


def _declarados():
    declarados = {}
    for prefixo, (_, definicoes) in TIPOS.items():
        for definicao in definicoes:
            declarados[f"{prefixo}_{definicao['campo']}"] = _campo(definicao)
        declarados[f"{prefixo}_{OUTROS}"] = CampoJSON(
            widget=ObjetoTema([], extras=True), required=False, label="Outros campos do ERP"
        )
    return declarados


def secao_endereco(prefixo, titulo, classes=()):
    """Secao do fieldsets com as linhas montadas pela largura (ate 12 colunas por linha)."""
    linhas, atual, soma = [], [], 0
    for definicao in TIPOS[prefixo][1]:
        largura = definicao.get("largura") or 6
        if atual and soma + largura > 12:
            linhas.append(tuple(atual))
            atual, soma = [], 0
        atual.append(f"{prefixo}_{definicao['campo']}")
        soma += largura
    linhas += [tuple(atual), f"{prefixo}_{OUTROS}"]
    return (titulo, {"classes": list(classes), "fields": linhas})


# Form so com os campos declarados: o ModelForm abaixo herda os campos dele.
CamposDeEndereco = type("CamposDeEndereco", (forms.Form,), _declarados())


class EnderecosForm(CamposDeEndereco, forms.ModelForm):
    """Subclasse define `endereco_inicial(tipo)` para preencher a tela na edicao."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for prefixo, (tipo, definicoes) in TIPOS.items():
            endereco = self.endereco_inicial(tipo) if self.instance.pk else None
            dados = enderecos.para_woo(endereco, {}) if endereco else {}
            chaves = {definicao["campo"] for definicao in definicoes}
            for chave in chaves:
                self.initial[f"{prefixo}_{chave}"] = dados.get(chave, "")
            self.initial[f"{prefixo}_{OUTROS}"] = {
                chave: valor for chave, valor in dados.items() if chave not in chaves
            }

    def endereco_inicial(self, tipo):
        return None

    def _dados(self, prefixo):
        definicoes = TIPOS[prefixo][1]
        dados = dict(self.cleaned_data.get(f"{prefixo}_{OUTROS}") or {})
        for definicao in definicoes:
            valor = self.cleaned_data.get(f"{prefixo}_{definicao['campo']}")
            dados[definicao["campo"]] = (valor or "").strip()
        return dados

    def clean(self):
        dados = super().clean()
        for prefixo in TIPOS:
            try:
                enderecos.aplicar(Address(), self._dados(prefixo), substituir=True).clean()
            except ValidationError as erro:
                for campo_modelo, mensagens in erro.message_dict.items():
                    chave = ERRO_PARA_CHAVE.get(campo_modelo)
                    if chave:
                        self.add_error(f"{prefixo}_{chave}", mensagens)
        return dados

    def enderecos_alterados(self):
        """[(tipo_woo, dados)] so dos enderecos que mudaram na tela."""
        return [
            (tipo, self._dados(prefixo))
            for prefixo, (tipo, _) in TIPOS.items()
            if any(nome.startswith(f"{prefixo}_") for nome in self.changed_data)
        ]
