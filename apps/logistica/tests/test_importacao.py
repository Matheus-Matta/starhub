"""Importar faixas de CEP por planilha: regras da linha, a tarefa e a tela."""

from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core import planilha
from apps.integracoes.importar_planilha import LinhaInvalida
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import argumentos
from apps.logistica.importacao import importar_faixa
from apps.logistica.models import FaixaCep, TabelaFrete
from apps.logistica.tasks import importar_faixas

pytestmark = pytest.mark.django_db
CABECALHO = "Tabela;CEP inicial;CEP final;Valor;Prazo dias\n"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _linha(**extra):
    return {"tabela": "Grande SP", "cep_inicial": "01000-000", "cep_final": "05999-999",
            "valor": "19,90", "prazo_dias": "2", **extra}


def test_cria_a_tabela_por_faixa_e_grava_cep_so_com_digitos():
    faixa, criada = importar_faixa(_linha())
    assert criada and faixa.tabela.tipo == "faixa_cep" and faixa.tabela.nome == "Grande SP"
    assert (faixa.cep_inicial, faixa.cep_final, faixa.valor, faixa.prazo_dias) == (
        "01000000", "05999999", Decimal("19.90"), 2)


def test_mesma_faixa_atualiza_valor_e_prazo_sem_duplicar():
    importar_faixa(_linha())
    faixa, criada = importar_faixa(_linha(tabela="grande sp", valor="R$ 1.234,50", prazo_dias=""))
    assert not criada and FaixaCep.objects.count() == 1 and TabelaFrete.objects.count() == 1
    assert (faixa.valor, faixa.prazo_dias) == (Decimal("1234.50"), None)


def test_faixa_que_cruza_outra_da_tabela_e_recusada():
    """O mesmo CEP em duas faixas: o cliente pagaria um de dois valores."""
    importar_faixa(_linha())
    with pytest.raises(LinhaInvalida, match="cruza com 01000000-05999999"):
        importar_faixa(_linha(cep_inicial="05000-000", cep_final="08999-999"))
    importar_faixa(_linha(tabela="Outra", cep_inicial="05000-000", cep_final="08999-999"))
    assert FaixaCep.objects.count() == 2  # em outra tabela pode


@pytest.mark.parametrize("campos,motivo", [
    ({"cep_inicial": "123"}, "8 digitos"), ({"valor": "abc"}, "valor"),
    ({"valor": "-5"}, "valor"), ({"prazo_dias": "dois"}, "prazo_dias"),
    ({"cep_inicial": "09000-000", "cep_final": "01000-000"}, "maior que"),
    ({"tabela": ""}, "nome da tabela"),
])
def test_linha_errada_diz_o_que_corrigir(campos, motivo):
    with pytest.raises(LinhaInvalida, match=motivo):
        importar_faixa(_linha(**campos))
    assert not FaixaCep.objects.exists()


def test_tabela_por_distancia_nao_recebe_faixa():
    TabelaFrete.objects.create(nome="Grande SP", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("2"))
    with pytest.raises(LinhaInvalida, match="por distancia"):
        importar_faixa(_linha())


def _tarefa(conteudo, **parametros):
    caminho = default_storage.save("importacoes/tabelafrete/t.csv", ContentFile(conteudo))
    execucao = ExecucaoIntegracao.objects.create(
        tipo=ExecucaoIntegracao.Tipo.IMPORTAR_FRETE,
        parametros={"arquivo": caminho, "nome": "t.csv", **parametros})
    importar_faixas.run(str(execucao.pk))
    execucao.refresh_from_db()
    return execucao


def test_tarefa_importa_as_boas_e_lista_a_que_cruza():
    execucao = _tarefa((CABECALHO + "Grande SP;01000-000;05999-999;19,90;2\n"
                        "Grande SP;06000-000;09999-999;24,90;\n"
                        "Grande SP;05000-000;06999-999;30,00;1\n").encode())
    assert execucao.status == "completed_errors" and "2 faixas criadas" in execucao.mensagem
    assert execucao.configuracao is None  # nao e tarefa de marketplace
    assert [f["motivo"][:8] for f in execucao.falhas] == ["Linha 4:"]


def test_substituir_apaga_as_faixas_antigas_da_tabela_da_planilha():
    """A planilha e a tabela inteira: faixa antiga que nao veio nela tem que sair."""
    importar_faixa(_linha(cep_inicial="20000-000", cep_final="20999-999"))
    importar_faixa(_linha(tabela="Intocada", cep_inicial="20000-000", cep_final="20999-999"))
    _tarefa((CABECALHO + "Grande SP;01000-000;05999-999;19,90;2\n").encode(), substituir=True)
    assert list(FaixaCep.objects.filter(tabela__nome="Grande SP").values_list(
        "cep_inicial", flat=True)) == ["01000000"]
    assert FaixaCep.objects.filter(tabela__nome="Intocada").count() == 1


def test_tela_botao_modelo_e_envio_criam_a_tarefa(admin_logado, django_capture_on_commit_callbacks):
    lista = reverse("admin:logistica_tabelafrete_changelist")
    assert "Importar planilha" in admin_logado.get(lista).content.decode()
    modelo = admin_logado.get(reverse("admin:logistica_tabelafrete_importar_modelo"))
    (_, exemplo), = planilha.ler(modelo.content, "modelo.csv")
    assert importar_faixa(exemplo)[1]  # o proprio modelo importa sem erro
    FaixaCep.objects.all().delete()
    arquivo = SimpleUploadedFile("faixas.csv", (CABECALHO + "SP;01000-000;05999-999;19,90;\n")
                                 .encode())
    with django_capture_on_commit_callbacks(execute=True):
        resposta = admin_logado.post(reverse("admin:logistica_tabelafrete_importar"),
                                     {"planilha": arquivo, "substituir": "on"})
    execucao = ExecucaoIntegracao.objects.get()
    assert resposta.url.endswith(f"/execucaointegracao/{execucao.pk}/change/")
    assert execucao.parametros["substituir"] is True and execucao.status == "completed"
    assert argumentos(execucao)[0].endswith("importar_faixas")
