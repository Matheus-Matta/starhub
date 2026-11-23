"""Exportar da lista de produtos: produto variavel sai com uma linha por variante.

A lista mostra o variavel numa linha so, com preco, SKU e estoque da variante padrao;
a exportacao repetia isso e as outras variacoes (M, G) nao apareciam no Excel nem no PDF.
"""

from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.models import Produto, VarianteProduto

pytestmark = pytest.mark.django_db


def _variante(produto, titulo, sku, preco, estoque, **campos):
    return VarianteProduto.objects.create(
        produto=produto, titulo=titulo, sku=sku, price=Decimal(preco),
        inventory_quantity=estoque, **campos)


@pytest.fixture
def produtos():
    camiseta = Produto.objects.create(nome="Camiseta", tipo=Produto.Tipo.VARIAVEL)
    _variante(camiseta, "P", "CAM-P", "49.90", 3)
    _variante(camiseta, "M", "CAM-M", "52.90", 0)
    _variante(camiseta, "G", "CAM-G", "54.90", 7)
    mesa = Produto.objects.create(nome="Mesa")
    padrao = mesa.variante_padrao
    padrao.sku, padrao.price, padrao.inventory_quantity = "MESA-1", Decimal("300"), 2
    padrao.save()
    return camiseta, mesa


def _linhas_do_excel(cliente, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    cliente.post(reverse("admin:loja_produto_exportar_relatorio"))
    tarefa = ExecucaoIntegracao.objects.get(tipo="export_report")
    assert tarefa.status == ExecucaoIntegracao.Status.CONCLUIDA, tarefa.mensagem
    resposta = cliente.get(reverse("admin:integracoes_execucaointegracao_arquivo",
                                   args=[tarefa.pk, "xlsx"]))
    planilha = load_workbook(BytesIO(b"".join(resposta.streaming_content))).active
    cabecalho, *linhas = list(planilha.values)
    preco = list(cabecalho).index("Preco") + 1
    assert "R$" in planilha.cell(row=2, column=preco).number_format
    return cabecalho, [dict(zip(cabecalho, linha, strict=True)) for linha in linhas], tarefa


def test_variavel_sai_com_uma_linha_por_variante(admin_logado, produtos, settings, tmp_path):
    camiseta, mesa = produtos
    _cabecalho, linhas, _tarefa = _linhas_do_excel(admin_logado, settings, tmp_path)

    por_sku = {linha["SKU"]: linha for linha in linhas}
    assert set(por_sku) == {"CAM-P", "CAM-M", "CAM-G", "MESA-1"}
    m = por_sku["CAM-M"]
    assert (m["ID"], m["Nome"], m["Variacao"]) == (camiseta.pk, "Camiseta", "M")
    # Numero no Excel (o openpyxl le como float): soma e filtra.
    assert (m["Preco"], m["Estoque"], m["Situacao do estoque"]) == (52.9, 0, "Sem estoque")
    assert (por_sku["CAM-G"]["Preco"], por_sku["CAM-G"]["Estoque"]) == (54.9, 7)
    assert (por_sku["MESA-1"]["ID"], por_sku["MESA-1"]["Variacao"]) == (mesa.pk, None)


def test_cada_dado_tem_a_sua_coluna(admin_logado, produtos, settings, tmp_path):
    """Nome, SKU e foto juntos numa celula (como na lista) nao filtram nem somam no
    Excel; duas colunas "Estoque" (quantidade e situacao) confundiam quem le."""
    cabecalho, _linhas, _tarefa = _linhas_do_excel(admin_logado, settings, tmp_path)

    assert list(cabecalho) == [
        "ID", "Nome", "Variacao", "SKU", "Codigo de barras", "Codigo externo", "Tipo",
        "Preco", "Preco promocional", "Estoque", "Situacao do estoque", "Status", "Ativo",
        "Alterado em",
    ]


def test_tarefa_conta_os_produtos_e_diz_quantas_linhas_saem(admin_logado, produtos, settings,
                                                             tmp_path):
    """O total e de produtos (o limite do relatorio e por registro); a mensagem explica
    por que a planilha tem mais linhas que produtos."""
    _cabecalho, linhas, tarefa = _linhas_do_excel(admin_logado, settings, tmp_path)

    assert len(linhas) == 4 and tarefa.total == 2
    assert "4 linha(s)" in tarefa.mensagem
