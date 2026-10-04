"""Tela de importar avaliacoes: botao na lista, modelo, envio do arquivo e a tarefa."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core import planilha
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.retomar import argumentos
from apps.loja.models import Avaliacao
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
LISTA = "/admin/loja/avaliacao/"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def test_lista_tem_o_botao_e_a_pagina_explica_as_colunas(admin_logado):
    assert "Importar planilha" in admin_logado.get(LISTA).content.decode()
    pagina = admin_logado.get(reverse("admin:loja_avaliacao_importar")).content.decode()
    assert "comentario" in pagina and "Baixar modelo" in pagina


def test_modelo_abre_no_excel_e_le_de_volta_na_importacao(admin_logado):
    """O modelo tem que ser aceito pela propria importacao, com acento e em colunas."""
    resposta = admin_logado.get(reverse("admin:loja_avaliacao_importar_modelo"))
    assert resposta["Content-Disposition"].endswith('modelo-avaliacoes.csv"')
    (_, linha), = planilha.ler(resposta.content, "modelo.csv")
    assert linha["email"] == "ana@exemplo.com" and linha["nota"] == "5"


def test_enviar_planilha_cria_a_tarefa_e_importa(admin_logado, conta,
                                                django_capture_on_commit_callbacks):
    """De ponta a ponta: upload -> tarefa -> avaliacao criada; a tela abre a tarefa."""
    ConfiguracaoIntegracao.objects.create(account=conta)
    criar_produto("Poltrona", sku="POL-001", price=Decimal("10.00"))
    arquivo = SimpleUploadedFile("minhas.csv", b"email;sku;nota;comentario\n"
                                               b"a@x.com;POL-001;5;Otima\n")
    with django_capture_on_commit_callbacks(execute=True):
        resposta = admin_logado.post(reverse("admin:loja_avaliacao_importar"),
                                     {"planilha": arquivo})
    execucao = ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.IMPORTAR_AVALIACOES)
    assert resposta.url == reverse("admin:integracoes_execucaointegracao_change",
                                   args=[execucao.pk])
    assert execucao.parametros["nome"] == "minhas.csv"
    assert ExecucaoIntegracao.objects.get(pk=execucao.pk).status == "completed"
    assert Avaliacao.objects.get().comentario == "Otima"


def test_sem_arquivo_valido_ou_sem_shopify_fica_na_pagina_com_o_motivo(admin_logado, conta):
    url = reverse("admin:loja_avaliacao_importar")
    resposta = admin_logado.post(url, {"planilha": SimpleUploadedFile("a.pdf", b"x")},
                                 follow=True)
    assert any(".xlsx ou .csv" in str(m) for m in resposta.context["messages"])
    resposta = admin_logado.post(url, {"planilha": SimpleUploadedFile("a.csv", b"email\n")},
                                 follow=True)
    assert any("integracao Shopify" in str(m) for m in resposta.context["messages"])
    assert not ExecucaoIntegracao.objects.exists()


def test_importacao_que_falhou_pode_ser_retomada(conta):
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=ConfiguracaoIntegracao.objects.create(account=conta),
        tipo=ExecucaoIntegracao.Tipo.IMPORTAR_AVALIACOES, status="failed",
        parametros={"arquivo": "importacoes/avaliacoes/x.csv"})
    caminho, args, _ = argumentos(execucao)
    assert caminho.endswith("importar_avaliacoes") and args == (str(execucao.pk),)
