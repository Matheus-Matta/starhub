"""Botao "Importar planilha" na lista de qualquer ModelAdmin, com pagina, modelo e tarefa.

    class TabelaFreteAdmin(ImportarPlanilhaMixin, TemaModelAdmin):
        importar_tipo = ExecucaoIntegracao.Tipo.IMPORTAR_FRETE
        importar_tarefa = "apps.logistica.tasks.importar_faixas"
        importar_colunas = [("tabela", True, "Nome da tabela"), ...]
        importar_exemplo = ["Grande SP", ...]

O arquivo vai para o MEDIA e a importacao roda numa tarefa (importar_planilha.py):
planilha grande nao prende a requisicao, e a tela da tarefa mostra a barra, as falhas
por linha e o Retomar. Rotas: <app>_<model>_importar e <app>_<model>_importar_modelo.
"""

import csv
import io
import uuid
from pathlib import PurePath

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import colocar_na_fila

TAMANHO_MAXIMO = 5 * 1024 * 1024


class ImportarPlanilhaMixin:
    change_list_template = "admin/change_list_importar.html"
    importar_tipo = None  # ExecucaoIntegracao.Tipo
    importar_tarefa = ""  # caminho da shared_task que recebe o id da execucao
    importar_colunas = []  # [(coluna, obrigatoria, o que vai nela)]
    importar_exemplo = []  # uma linha de exemplo no modelo, na ordem das colunas
    importar_arquivo_modelo = "modelo.csv"
    importar_descricao = ""
    importar_regras = []  # frases do card "Como funciona"
    importar_opcoes = []  # [(nome, rotulo)]: caixas de marcar gravadas em parametros

    def _rota(self, sufixo):
        opcoes = self.model._meta
        return f"{opcoes.app_label}_{opcoes.model_name}_{sufixo}"

    def get_urls(self):
        rotas = [
            path("importar/", self.admin_site.admin_view(self.importar_view),
                 name=self._rota("importar")),
            path("importar/modelo/", self.admin_site.admin_view(self.modelo_view),
                 name=self._rota("importar_modelo")),
        ]
        return [*rotas, *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        # O contexto da lista do Django nao traz has_change_permission: vai aqui.
        contexto = {**(extra_context or {}),
                    "url_importar": reverse(f"admin:{self._rota('importar')}"),
                    "pode_importar": self.has_change_permission(request)}
        return super().changelist_view(request, contexto)

    def modelo_view(self, request):
        saida = io.StringIO()
        # ; e BOM: o Excel em portugues abre direto, com acento e em colunas.
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow([coluna for coluna, _, _ in self.importar_colunas])
        escritor.writerow(self.importar_exemplo)
        resposta = HttpResponse("﻿" + saida.getvalue(), content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = f'attachment; filename="{self.importar_arquivo_modelo}"'
        return resposta

    def importar_configuracao(self, request):
        """Configuracao da tarefa; levante ValueError com o motivo para recusar."""
        return None

    def importar_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            resposta = self._receber(request)
            if resposta is not None:
                return resposta
        opcoes = self.model._meta
        contexto = {
            **self.admin_site.each_context(request), "opts": opcoes,
            "title": f"Importar {opcoes.verbose_name_plural}",
            "descricao": self.importar_descricao, "colunas": self.importar_colunas,
            "regras": self.importar_regras, "opcoes": self.importar_opcoes,
            "url_modelo": reverse(f"admin:{self._rota('importar_modelo')}"),
            "url_lista": reverse(f"admin:{opcoes.app_label}_{opcoes.model_name}_changelist"),
        }
        return TemplateResponse(request, "admin/importar_planilha.html", contexto)

    def _receber(self, request):
        """Grava o arquivo e cria a tarefa; None = erro mostrado na propria pagina."""
        arquivo = request.FILES.get("planilha")
        extensao = PurePath(getattr(arquivo, "name", "")).suffix.lower()
        if arquivo is None or extensao not in (".xlsx", ".csv"):
            messages.error(request, "Escolha uma planilha .xlsx ou .csv.")
            return None
        if arquivo.size > TAMANHO_MAXIMO:
            messages.error(request, "A planilha passa de 5 MB; divida em partes.")
            return None
        try:
            configuracao = self.importar_configuracao(request)
        except ValueError as erro:
            messages.error(request, str(erro))
            return None
        pasta = f"importacoes/{self.model._meta.model_name}"
        caminho = default_storage.save(f"{pasta}/{uuid.uuid4().hex}{extensao}", arquivo)
        parametros = {"arquivo": caminho, "nome": arquivo.name[:150]}
        parametros |= {nome: request.POST.get(nome) == "on" for nome, _ in self.importar_opcoes}
        execucao = ExecucaoIntegracao.objects.create(
            configuracao=configuracao, tipo=self.importar_tipo, etapa="Na fila",
            parametros=parametros)
        tarefa = self.importar_tarefa
        transaction.on_commit(lambda: colocar_na_fila(execucao.pk, tarefa, (str(execucao.pk),)))
        messages.success(request, f"Importacao de {arquivo.name} enviada para a fila.")
        return HttpResponseRedirect(
            reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))
