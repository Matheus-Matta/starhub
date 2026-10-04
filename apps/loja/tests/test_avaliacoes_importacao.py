"""Importar avaliacoes por planilha: leitura, regras de cada linha e a tarefa."""

import io
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.core import planilha
from apps.integracoes import permissoes
from apps.integracoes.envio import distribuidor
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Avaliacao, Cliente
from apps.loja.services.avaliacoes_importacao import LinhaInvalida, importar_linha
from apps.loja.services.variantes import criar_produto
from apps.loja.tasks import importar_avaliacoes

pytestmark = pytest.mark.django_db
CABECALHO = "E-mail;Nome;Sobrenome;SKU;Nota;Comentário;Status;Data\n"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def produto():
    return criar_produto("Poltrona", sku="POL-001", price=Decimal("10.00"))


@pytest.fixture
def enviados(monkeypatch, conta):
    """Shopify com envio de clientes e avaliacoes ligado; guarda o que iria para la."""
    matriz = permissoes.matriz_vazia()
    for recurso in ("clientes", "avaliacoes"):
        matriz["enviar"][recurso] = {"get": False, "create": True, "update": True, "delete": True}
    ConfiguracaoIntegracao.objects.create(account=conta, permissoes=matriz)
    fila = []
    monkeypatch.setattr(distribuidor, "_enfileirar", lambda *args: fila.append(args[1]))
    return fila


def _linha(**extra):
    return {"email": "ana@exemplo.com", "nome": "Ana", "sobrenome": "Lima", "sku": "POL-001",
            "nota": "5", "comentario": "Linda", **extra}


def test_csv_do_excel_com_bom_ponto_e_virgula_e_acento_no_cabecalho():
    conteudo = ("﻿" + CABECALHO + "a@x.com;Ana;Lima;POL-001;5;Ótima;;\n;;;;;;;\n").encode()
    linhas = planilha.ler(conteudo, "avaliacoes.csv")
    assert linhas == [(2, {"e_mail": "a@x.com", "nome": "Ana", "sobrenome": "Lima",
                           "sku": "POL-001", "nota": "5", "comentario": "Ótima",
                           "status": "", "data": ""})]


def test_xlsx_com_numero_e_data_do_excel():
    """O Excel grava a nota 5 como 5.0 e a data como data, nao como texto."""
    from openpyxl import Workbook

    livro = Workbook()
    livro.active.append(["email", "nota", "data"])
    livro.active.append(["a@x.com", 5.0, date(2026, 9, 15)])
    saida = io.BytesIO()
    livro.save(saida)
    assert planilha.ler(saida.getvalue(), "a.xlsx") == [
        (2, {"email": "a@x.com", "nota": "5", "data": "2026-09-15"})]


def test_formato_errado_e_recusado():
    with pytest.raises(planilha.PlanilhaInvalida, match=".xlsx ou .csv"):
        planilha.ler(b"x", "avaliacoes.pdf")


def test_linha_cria_cliente_so_no_hub_e_a_avaliacao_aprovada_vai_para_a_loja(
        produto, enviados, django_capture_on_commit_callbacks):
    """Cliente da planilha so assina a avaliacao: virar conta na loja mandaria e-mail."""
    with django_capture_on_commit_callbacks(execute=True):
        avaliacao, criada = importar_linha(_linha())
    assert criada and avaliacao.status == "aprovada" and avaliacao.origin == "import"
    assert avaliacao.nome_publico == "Ana L."
    assert Cliente.objects.get(email="ana@exemplo.com").origin == "import"
    assert enviados == ["avaliacoes"]


def test_importar_de_novo_atualiza_em_vez_de_duplicar(produto):
    importar_linha(_linha())
    avaliacao, criada = importar_linha(_linha(nota="3", comentario="Mudei de ideia"))
    assert not criada and Avaliacao.objects.count() == 1
    assert (avaliacao.nota, avaliacao.comentario) == (3, "Mudei de ideia")


def test_cliente_que_ja_existe_e_reaproveitado_sem_mudar_o_cadastro(produto):
    existente = Cliente.objects.create(email="ana@exemplo.com", nome="Ana Maria")
    avaliacao, _ = importar_linha(_linha(nome="Outro"))
    assert avaliacao.cliente == existente
    assert Cliente.objects.get(pk=existente.pk).nome == "Ana Maria"


def test_data_status_e_nome_publico_da_planilha(produto):
    avaliacao, _ = importar_linha(_linha(data="15/09/2026", status="Pendente",
                                         nome_publico="Cliente fiel"))
    avaliacao.refresh_from_db()
    assert timezone.localdate(avaliacao.created_at) == date(2026, 9, 15)
    assert avaliacao.status == "pendente" and avaliacao.moderado_em is None
    assert avaliacao.nome_publico == "Cliente fiel"


@pytest.mark.parametrize("campos,motivo", [
    ({"nota": "9"}, "nota de 1 a 5"), ({"email": "sem-arroba"}, "e-mail invalido"),
    ({"sku": "NAO-EXISTE"}, "produto nao encontrado"), ({"status": "talvez"}, "status"),
    ({"data": "31/02/2026"}, "dd/mm/aaaa"), ({"comentario": ""}, "comentario"),
])
def test_linha_errada_diz_o_que_corrigir(produto, campos, motivo):
    with pytest.raises(LinhaInvalida, match=motivo):
        importar_linha(_linha(**campos))
    assert not Avaliacao.objects.exists()


def test_tarefa_importa_as_boas_e_lista_as_linhas_com_erro(produto, conta):
    conteudo = (CABECALHO + "a@x.com;Ana;;POL-001;5;Boa;;\n"
                "b@x.com;Bia;;POL-001;9;Nota errada;;\n"
                "c@x.com;Caio;;POL-001;4;Ok;pendente;\n").encode()
    caminho = default_storage.save("importacoes/avaliacoes/t.csv", ContentFile(conteudo))
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=ConfiguracaoIntegracao.objects.create(account=conta),
        tipo=ExecucaoIntegracao.Tipo.IMPORTAR_AVALIACOES,
        parametros={"arquivo": caminho, "nome": "t.csv"})

    importar_avaliacoes.run(str(execucao.pk))

    execucao.refresh_from_db()
    assert execucao.status == "completed_errors" and execucao.progresso == 100
    assert "2 avaliacoes criadas" in execucao.mensagem
    assert [f["motivo"][:8] for f in execucao.falhas] == ["Linha 3:"]
    assert Avaliacao.objects.count() == 2
