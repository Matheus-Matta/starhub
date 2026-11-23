"""Exportacao generica da listagem pelos mesmos filtros visiveis no admin."""

from datetime import datetime
from io import BytesIO

import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.core.admin_base import TemaMixin
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import argumentos
from apps.loja.models import Tag

pytestmark = pytest.mark.django_db


def _url_exportar(query=""):
    url = reverse("admin:loja_tag_exportar_relatorio")
    return f"{url}?{query}" if query else url


def _conteudo(resposta):
    return b"".join(resposta.streaming_content)


@pytest.fixture
def tags():
    itens = [
        Tag.objects.create(nome="Incluida A"),
        Tag.objects.create(nome="Incluida B"),
        Tag.objects.create(nome="Fora do filtro"),
    ]
    Tag.objects.filter(pk__in=[itens[0].pk, itens[1].pk]).update(
        created_at=timezone.make_aware(datetime(2026, 9, 15, 12))
    )
    Tag.objects.filter(pk=itens[2].pk).update(
        created_at=timezone.make_aware(datetime(2026, 1, 15, 12))
    )
    return itens


def test_botao_de_exportar_fica_ao_lado_dos_filtros_e_preserva_a_busca(
        admin_logado, tags):
    """Perder a query no botao faria o arquivo levar registros que a tela escondeu."""
    html = admin_logado.get(
        reverse("admin:loja_tag_changelist") + "?q=Incluida"
    ).content.decode()
    ferramentas = html.split('class="list-card-tools"', 1)[1].split("</header>", 1)[0]

    assert "Exportar" in ferramentas and "Filtros" in ferramentas
    assert f'action="{_url_exportar("q=Incluida")}"' in ferramentas
    assert admin_logado.get(_url_exportar("q=Incluida")).status_code == 405


def test_todo_model_admin_do_tema_recebe_a_rota_generica():
    """Model novo nao pode depender de alguem lembrar de implementar sua exportacao."""
    for model, model_admin in admin.site._registry.items():
        if isinstance(model_admin, TemaMixin):
            nome = f"admin:{model._meta.app_label}_{model._meta.model_name}_exportar_relatorio"
            assert reverse(nome).endswith("/exportar-relatorio/")


def test_tarefa_exporta_todas_as_linhas_filtradas_em_excel_e_pdf(
        admin_logado, tags, settings, tmp_path, monkeypatch):
    """A exportacao usa o queryset inteiro filtrado, nao apenas a pagina aberta."""
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(admin.site._registry[Tag], "list_per_page", 1)

    resposta = admin_logado.post(_url_exportar("created_at__date__gte=2026-09-01"))

    tarefa = ExecucaoIntegracao.objects.get(tipo="export_report")
    assert resposta.status_code == 302
    assert resposta.url == reverse(
        "admin:integracoes_execucaointegracao_change", args=[tarefa.pk]
    )
    assert tarefa.status == ExecucaoIntegracao.Status.CONCLUIDA
    assert tarefa.total == 2 and tarefa.processados == 2

    xlsx = admin_logado.get(reverse(
        "admin:integracoes_execucaointegracao_arquivo", args=[tarefa.pk, "xlsx"]
    ))
    assert xlsx.status_code == 200 and "attachment" in xlsx["Content-Disposition"]
    linhas = list(load_workbook(BytesIO(_conteudo(xlsx))).active.values)
    nomes = {linha[0] for linha in linhas[1:]}
    assert nomes == {"Incluida A", "Incluida B"}

    pdf = admin_logado.get(reverse(
        "admin:integracoes_execucaointegracao_arquivo", args=[tarefa.pk, "pdf"]
    ))
    assert pdf.status_code == 200 and _conteudo(pdf).startswith(b"%PDF")

    detalhe = admin_logado.get(resposta.url).content.decode()
    assert "Baixar Excel" in detalhe and "Baixar PDF" in detalhe


def test_tarefa_ainda_aberta_nao_oferece_arquivo(admin_logado):
    """O botao de download antes do fim apontaria para um arquivo ainda inexistente."""
    # Model valido e arquivo ja registrado (ex.: tarefa reaberta): so o status aberto barra.
    tarefa = ExecucaoIntegracao.objects.create(
        tipo="export_report",
        parametros={
            "modelo": "loja.tag",
            "arquivos": {"xlsx": {"caminho": "relatorios/x/antigo.xlsx", "nome": "antigo.xlsx"}},
        },
    )

    html = admin_logado.get(reverse(
        "admin:integracoes_execucaointegracao_change", args=[tarefa.pk]
    )).content.decode()

    assert "Baixar Excel" not in html and "Baixar PDF" not in html
    assert admin_logado.get(reverse(
        "admin:integracoes_execucaointegracao_arquivo", args=[tarefa.pk, "xlsx"]
    )).status_code == 404


def test_exportacao_que_falhou_pode_ser_retomada_com_os_mesmos_filtros():
    """Falha de storage ou worker nao deve obrigar o operador a montar o filtro de novo."""
    parametros = {"modelo": "loja.tag", "query": "q=Incluida", "usuario_id": 1}
    tarefa = ExecucaoIntegracao.objects.create(
        tipo="export_report", status="failed", parametros=parametros
    )

    caminho, args, kwargs = argumentos(tarefa)

    assert caminho == "apps.core.tasks.exportar_relatorio"
    assert args == (str(tarefa.pk),) and kwargs == {}
