"""Widgets para campos JSON (tags, metadados, imagens, listas, objetos).

O valor enviado continua sendo o JSON num <textarea> escondido; o JS do tema
(static/starhub/js/json-*.js) monta a interface a partir de `data-config` e
reescreve o JSON a cada mudanca. No servidor, CampoJSON revalida o formato
com a funcao de normalizacao do tipo (apps/core/json_normalizar.py).

Uso no ModelAdmin do tema:
    campos_json = {"tags": TagsTema(), "metadados": ChaveValorTema()}
"""

import json

from django import forms

from apps.core import imagens, json_normalizar


class JSONTema(forms.Textarea):
    template_name = "core/widgets/json.html"
    tipo = ""
    # Ocupa as duas colunas do formulario (tabelas, endereco, imagens).
    largo = True

    def config(self):
        return {}

    def normalizar(self, valor, rotulo):
        return valor

    def get_context(self, name, value, attrs):
        contexto = super().get_context(name, value, attrs)
        contexto["widget"]["tipo"] = self.tipo
        contexto["widget"]["config_json"] = json.dumps(self.config())
        return contexto


class TagsTema(JSONTema):
    """Etiquetas criadas na hora (Enter, virgula ou Tab). `sugestoes` e uma
    funcao chamada a cada abertura da tela (ex.: tags ja usadas).

    simples=False: formato Woo, [{"id", "name"}]. simples=True: ["read", "write"].
    """

    tipo = "tags"
    largo = False  # tags e campo de texto: uma coluna

    def __init__(self, sugestoes=None, simples=False, attrs=None):
        super().__init__(attrs)
        self.sugestoes = sugestoes
        self.simples = simples

    def config(self):
        sugestoes = list(self.sugestoes() if callable(self.sugestoes) else self.sugestoes or [])
        return {"sugestoes": sugestoes, "simples": self.simples}

    def normalizar(self, valor, rotulo):
        return json_normalizar.textos(valor) if self.simples else json_normalizar.tags(valor)


class ChaveValorTema(JSONTema):
    tipo = "chave-valor"

    def normalizar(self, valor, rotulo):
        return json_normalizar.chave_valor(valor)


class ListaTema(JSONTema):
    """Tabela de linhas. colunas: [{"campo", "rotulo", "tipo"}], com tipo em
    texto | numero | dinheiro | switch | tags."""

    tipo = "lista"

    def __init__(self, colunas, com_id=False, botao="Adicionar linha", attrs=None):
        super().__init__(attrs)
        self.colunas = colunas
        self.com_id = com_id
        self.botao = botao

    def config(self):
        return {"colunas": self.colunas, "botao": self.botao}

    def normalizar(self, valor, rotulo):
        return json_normalizar.lista(valor, self.colunas, rotulo, self.com_id)


class ObjetoTema(JSONTema):
    """Grade de campos fixos (endereco, dimensoes); extras=True mostra e guarda
    os campos que nao estao na lista ("outros campos")."""

    tipo = "objeto"

    def __init__(self, campos, extras=True, colunas=2, attrs=None):
        super().__init__(attrs)
        self.campos = campos
        self.extras = extras
        self.colunas = colunas

    def config(self):
        return {"campos": self.campos, "extras": self.extras, "colunas": self.colunas}

    def normalizar(self, valor, rotulo):
        return json_normalizar.objeto(valor, self.campos, self.extras, rotulo)


class ValorComArquivos(str):
    """O JSON do campo + os arquivos enviados junto (widget de imagens)."""

    arquivos = ()


class ImagensTema(JSONTema):
    tipo = "imagens"
    needs_multipart_form = True

    def __init__(self, multiplas=True, pasta="imagens", attrs=None):
        super().__init__(attrs)
        self.multiplas = multiplas
        self.pasta = pasta

    def config(self):
        return {"multiplas": self.multiplas}

    def get_context(self, name, value, attrs):
        contexto = super().get_context(name, value, attrs)
        contexto["widget"]["multiplas"] = self.multiplas
        return contexto

    def value_from_datadict(self, data, files, name):
        valor = ValorComArquivos(data.get(name) or ("[]" if self.multiplas else "null"))
        valor.arquivos = files.getlist(f"{name}__arquivos") if files else []
        return valor

    def normalizar(self, valor, rotulo):
        lista = valor if isinstance(valor, list) else ([valor] if isinstance(valor, dict) else [])
        lista = [dict(item) for item in lista if isinstance(item, dict) and item.get("src")]
        if self.multiplas:
            return lista
        return lista[0] if lista else None


class CampoJSON(forms.JSONField):
    def has_changed(self, initial, data):
        # Arquivo enviado nao muda o texto do campo ("[]" continua "[]"): sem isto o
        # form achava que nada mudou e a imagem subia para o disco sem ser ligada a nada.
        if getattr(data, "arquivos", None):
            return True
        return super().has_changed(initial, data)

    def clean(self, value):
        arquivos = getattr(value, "arquivos", ())
        dados = self.widget.normalizar(super().clean(value), str(self.label or "Campo"))
        if not arquivos:
            return dados
        # Arquivo so e gravado depois que o JSON do campo passou na validacao.
        novas = [imagens.salvar(arquivo, self.widget.pasta) for arquivo in arquivos]
        if self.widget.multiplas:
            return [*dados, *novas]
        return novas[-1]


def widget_padrao(db_field):
    """Widget de um campo JSON que o ModelAdmin nao declarou em campos_json.

    Assim nenhum JSON aparece cru: metadados do Woo viram chave = valor e
    dicionario livre (configuracoes, dados extras) vira chave = valor tambem.
    Lista de formato proprio (sem padrao aqui) precisa ser declarada.
    """
    if db_field.name == "metadados":
        return ChaveValorTema()
    if db_field.default is dict:
        return ObjetoTema([], extras=True)
    return None


def campo_json(db_field, widget, **kwargs):
    """Form field do ModelAdmin para um JSONField com widget do tema."""
    # O JSONField do model ja repassa encoder/decoder para o form_class.
    return db_field.formfield(form_class=CampoJSON, widget=widget, **kwargs)
