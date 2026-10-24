"""Importar e exportar servicos (com as regras) por planilha, na lista de Servicos.

Importar usa a tela, o modelo e a tarefa de toda importacao
(apps/integracoes/admin_importar.py). Exportar baixa o .xlsx na hora com as mesmas
colunas: editar a planilha exportada e importar de volta atualiza, sem duplicar.
"""

from io import BytesIO

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils import timezone

from apps.integracoes.admin_importar import ImportarPlanilhaMixin
from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.services import servicos_planilha

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class PlanilhaServicosMixin(ImportarPlanilhaMixin):
    importar_tipo = ExecucaoIntegracao.Tipo.IMPORTAR_SERVICOS
    importar_tarefa = "apps.loja.tasks.importar_servicos"
    importar_arquivo_modelo = "modelo-servicos.csv"
    importar_descricao = "Cria e atualiza os servicos e as regras de cada um."
    importar_colunas = servicos_planilha.COLUNAS
    importar_exemplo = servicos_planilha.EXEMPLO
    importar_regras = [
        "Uma linha por regra; os dados do servico se repetem. Servico sem regra: deixe "
        "regra_ordem vazia.",
        "O servico e achado pelo SKU e, sem ele, pelo nome; a regra, pela ordem dentro dele: "
        "importar de novo a planilha exportada (ou corrigida) atualiza, nao duplica.",
        "Na coluna produtos vale o SKU, o handle (ex.: sofa-retratil-cinza) ou o titulo do "
        "produto. Titulo repetido em dois produtos e recusado: use o SKU ou o handle.",
        "Regra por categoria usa a coluna categorias (e a faixa de preco, opcional); por "
        "produto, a coluna produtos. A outra coluna e ignorada.",
        "Linha com erro nao para as outras: a tarefa lista cada uma com o motivo.",
    ]

    def get_urls(self):
        rota = f"{self.model._meta.app_label}_{self.model._meta.model_name}_exportar"
        return [path("exportar/", self.admin_site.admin_view(self.exportar_view), name=rota),
                *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        contexto = {**(extra_context or {}),
                    "url_exportar_planilha": reverse("admin:loja_servico_exportar")}
        return super().changelist_view(request, contexto)

    def exportar_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        arquivo = BytesIO()
        servicos_planilha.planilha().save(arquivo)
        resposta = HttpResponse(arquivo.getvalue(), content_type=XLSX)
        nome = f"servicos-{timezone.localdate():%Y-%m-%d}.xlsx"
        resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return resposta
