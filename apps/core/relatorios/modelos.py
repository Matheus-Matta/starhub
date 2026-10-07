"""Relatorio generico de um model: as colunas e o filtro da lista do proprio admin.

Usar a `list_display` do ModelAdmin faz o relatorio acompanhar a tela: coluna nova
na lista aparece no Excel e no PDF sem configurar nada. O queryset tambem e o do
admin, entao conta (tenant) e superusuario valem igual a lista.
"""

from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.admin.utils import display_for_field, label_for_field, lookup_field
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import models
from django.utils.text import capfirst, slugify

from apps.core.admin_base import campo_de_criacao
from apps.core.relatorios.base import Relatorio, Resultado, Tabela, local, no_periodo

# Colunas de tela (marcar linha, botoes) que nao sao dado.
FORA = {"action_checkbox", "acoes"}
NUMERO_OU_DATA = (models.DecimalField, models.IntegerField, models.DateField)


class _SoDado(HTMLParser):
    """Texto de uma celula HTML sem o que o tema marca como decorativo
    (aria-hidden: iniciais do avatar, icones): "AL Ana Lima" vira "Ana Lima"."""

    VAZIOS = {"img", "br", "input", "use", "path", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes, self.pilha = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VAZIOS:
            oculto = dict(attrs).get("aria-hidden") == "true"
            self.pilha.append(oculto or bool(self.pilha and self.pilha[-1]))

    def handle_endtag(self, tag):
        if tag not in self.VAZIOS and self.pilha:
            self.pilha.pop()

    def handle_data(self, dados):
        if not (self.pilha and self.pilha[-1]):
            self.partes.append(dados)


def _texto(valor):
    leitor = _SoDado()
    leitor.feed(str(valor))
    leitor.close()
    return " ".join(" ".join(leitor.partes).split())


def _campo_por_tras(model, attr):
    """Coluna-metodo ordenada por um campo numerico/data do proprio model ("total_fmt"
    com ordering="total"): o Excel recebe esse valor, que soma e filtra."""
    nome = getattr(attr, "admin_order_field", None)
    if not isinstance(nome, str) or "__" in nome or nome.startswith("-"):
        return None
    try:
        campo = model._meta.get_field(nome)
    except FieldDoesNotExist:
        return None
    if campo.choices or not isinstance(campo, NUMERO_OU_DATA):
        return None
    return campo


def _celula(model_admin, obj, nome):
    """(valor, mostra em reais?) de uma coluna da lista."""
    try:
        campo, attr, valor = lookup_field(nome, obj, model_admin)
    except (AttributeError, ObjectDoesNotExist):
        return "", False
    if campo is None and (por_tras := _campo_por_tras(type(obj), attr)):
        return local(getattr(obj, por_tras.attname)), "R$" in _texto(valor)
    if campo is not None and getattr(campo, "choices", None):
        return _texto(display_for_field(valor, campo, "")), False
    if isinstance(valor, bool):
        return ("Sim" if valor else "Nao"), False
    if valor is None:
        return "", False
    if isinstance(valor, (Decimal, int, date)):
        return local(valor), False
    return _texto(valor), False


class RelatorioModelo(Relatorio):
    def __init__(self, model, model_admin, icone):
        opcoes = model._meta
        self.model, self.model_admin, self.icone = model, model_admin, icone
        self.chave = opcoes.label_lower
        self.titulo = capfirst(opcoes.verbose_name_plural)
        self.descricao = f"Cadastro de {opcoes.verbose_name_plural} pela data de criacao."
        self.nome_arquivo = slugify(opcoes.verbose_name_plural)

    def permitido(self, request):
        return self.model_admin.has_view_or_change_permission(request)

    def _colunas(self, request):
        return [nome for nome in self.model_admin.get_list_display(request) if nome not in FORA]

    def _consulta(self, request, de, ate):
        admin = self.model_admin
        consulta = admin.get_queryset(request)
        campo = campo_de_criacao(admin)
        if campo:
            consulta = consulta.filter(**no_periodo(campo, de, ate))
        relacionados = admin.get_list_select_related(request)
        if relacionados is True:
            consulta = consulta.select_related()
        elif relacionados:
            consulta = consulta.select_related(*relacionados)
        ordem = admin.get_ordering(request) or self.model._meta.ordering or ["-pk"]
        return consulta.order_by(*ordem)

    def gerar(self, request, de, ate, limite):
        nomes = self._colunas(request)
        consulta = self._consulta(request, de, ate)
        tabela = Tabela(self.titulo, [
            capfirst(_texto(label_for_field(nome, self.model, self.model_admin)))
            for nome in nomes
        ])
        for obj in consulta[:limite]:
            celulas = [_celula(self.model_admin, obj, nome) for nome in nomes]
            tabela.linhas.append([valor for valor, _reais in celulas])
            tabela.moeda |= {indice for indice, (_v, reais) in enumerate(celulas) if reais}
        return Resultado(tabela, consulta.count())
