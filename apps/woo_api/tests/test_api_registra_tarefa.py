"""A API Woo registra tarefa: escrita sempre, leitura so com erro, e liga ao registro."""

import pytest
from auditlog.models import LogEntry

from apps.core import registros
from apps.integracoes.models import ExecucaoIntegracao, TarefaRegistro
from apps.loja.models import Produto
from apps.loja.services.variantes import criar_produto
from apps.woo_api.tests.conftest import cliente_com_chave

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/products"
Status = ExecucaoIntegracao.Status


def _tarefas():
    return ExecucaoIntegracao.objects.filter(tipo=ExecucaoIntegracao.Tipo.API_WOO)


def test_escrita_vira_tarefa_com_requisicao_resposta_e_o_produto_ligado(api):
    resposta = api.post(URL, {"name": "Armario", "sku": "ARM-1"}, format="json")

    assert resposta.status_code == 201
    tarefa = _tarefas().get()
    produto = Produto.objects.get()
    assert tarefa.status == Status.CONCLUIDA and tarefa.etapa == "HTTP 201"
    assert tarefa.parametros["requisicao"]["metodo"] == "POST"
    assert tarefa.parametros["requisicao"]["corpo"] == {"name": "Armario", "sku": "ARM-1"}
    assert tarefa.parametros["resposta"]["corpo"]["id"] == produto.pk
    # Credencial nunca vai para a tela de tarefas.
    assert "Authorization" not in tarefa.parametros["requisicao"]["cabecalhos"]
    # O log da escrita aponta para a tarefa e a correlacao junta tudo que ela fez.
    log = LogEntry.objects.get_for_object(produto).first()
    assert log.additional_data["tarefa_id"] == tarefa.pk and log.cid == f"tarefa-{tarefa.pk}"
    assert log.additional_data["requisicao"]["caminho"] == URL
    # O produto e a variante criada junto ficam ligados a tarefa.
    ligados = set(TarefaRegistro.objects.filter(execucao=tarefa)
                  .values_list("content_type__model", flat=True))
    assert {"produto", "varianteproduto"} <= ligados


def test_botao_tarefas_do_produto_acha_a_requisicao_que_alterou_a_variante(api, admin_logado):
    produto = criar_produto("Mesa", sku="MESA-1")
    # O preco mora na variante padrao: o PUT do produto altera a variante.
    resposta = api.put(f"/wp-json/wc/v1/products/{produto.pk}", {"regular_price": "99.90"},
                       format="json")
    assert resposta.status_code == 200
    tarefa = _tarefas().get()
    lista_url = "/admin/integracoes/execucaointegracao/"

    pelo_produto = admin_logado.get(lista_url, {"registro": registros.chave(produto)})
    pela_variante = admin_logado.get(
        lista_url, {"registro": registros.SO + registros.chave(produto.variante_padrao)})
    outro = admin_logado.get(lista_url, {"registro": registros.chave(criar_produto("X", sku="X"))})

    assert [t.pk for t in pelo_produto.context["cl"].result_list] == [tarefa.pk]
    assert [t.pk for t in pela_variante.context["cl"].result_list] == [tarefa.pk]
    assert not list(outro.context["cl"].result_list)
    pagina = admin_logado.get(f"/admin/integracoes/execucaointegracao/{tarefa.pk}/change/")
    assert "Registros afetados" in pagina.content.decode()
    assert "Logs desta tarefa" in pagina.content.decode()


def test_recusa_vira_tarefa_falhou_com_o_codigo_do_woo(api):
    resposta = api.put(f"{URL}/999999", {"name": "X"}, format="json")

    assert resposta.status_code == 404
    tarefa = _tarefas().get()
    assert tarefa.status == Status.FALHOU
    assert tarefa.mensagem.startswith("HTTP 404 woocommerce_rest_product_invalid_id")
    assert tarefa.falhas[0]["motivo"] == tarefa.mensagem


def test_leitura_so_vira_tarefa_quando_falha(api):
    assert api.get(URL).status_code == 200
    assert not _tarefas().exists()

    assert api.get(f"{URL}/999999").status_code == 404
    assert _tarefas().get().status == Status.FALHOU


def test_chave_so_de_leitura_tentando_escrever_fica_registrada(par_somente_leitura):
    """A recusa de permissao (403) era a que o operador mais procurava e nao achava."""
    cliente = cliente_com_chave(*par_somente_leitura)

    resposta = cliente.post(URL, {"name": "Y"}, format="json")

    assert resposta.status_code in (401, 403)
    tarefa = _tarefas().get()
    assert tarefa.status == Status.FALHOU and not Produto.objects.exists()


def test_item_recusado_no_lote_deixa_a_tarefa_concluida_com_falhas(api):
    existente = criar_produto("Ok", sku="OK-1")
    corpo = {"update": [{"id": existente.pk, "name": "Ok 2"}, {"id": 999999, "name": "Z"}]}

    assert api.post(f"{URL}/batch", corpo, format="json").status_code == 200

    tarefa = _tarefas().get()
    assert tarefa.status == Status.CONCLUIDA_COM_FALHAS
    assert [falha["recurso"] for falha in tarefa.falhas] == ["update"]
    assert tarefa.falhas[0]["id"] == "999999"


def test_senha_no_corpo_nao_vai_para_a_tarefa(api):
    api.post("/wp-json/wc/v1/customers",
             {"email": "a@b.test", "password": "segredo-123"}, format="json")
    corpo = _tarefas().get().parametros["requisicao"]["corpo"]
    assert corpo["password"] == "***" and corpo["email"] == "a@b.test"


def test_versao_do_historico_gravada_pela_api_diz_a_chave_e_a_tarefa(api):
    """A versao da API ficava sem autor e sem motivo: nao dava para saber de onde veio."""
    api.post(URL, {"name": "Rack", "sku": "RAC-1"}, format="json")
    tarefa = _tarefas().get()
    versao = Produto.objects.get().historical.first()
    assert versao.history_change_reason.startswith("woo_api - ERP (...")
    assert versao.history_change_reason.endswith(f"tarefa #{tarefa.pk}")
