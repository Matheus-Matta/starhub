"""Logs que dizem alguma coisa: filtro com os itens relacionados e a tela do log legivel."""

from types import SimpleNamespace

import pytest
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType

from apps.core import registros
from apps.core.models import User
from apps.core.origem import origem, requisicao_de
from apps.core.tenant.context import tenant_context
from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
LISTA = "/admin/auditlog/logentry/"


def _tipos(resposta):
    return {log.content_type.model_class() for log in resposta.context["cl"].result_list}


@pytest.fixture
def produto_com_variante_alterada(conta):
    produto = criar_produto("Armario", sku="ARM-1")
    variante = produto.variante_padrao
    variante.sku = "ARM-1-BRANCO"
    variante.save()
    return produto, variante


def test_logs_do_produto_incluem_os_da_variante(admin_logado, produto_com_variante_alterada):
    """A variante abre num modal sem botao de logs: sem isto o log dela era inalcancavel."""
    produto, variante = produto_com_variante_alterada
    chave = registros.chave(produto)

    com_itens = admin_logado.get(LISTA, {"registro": chave})
    so_ele = admin_logado.get(LISTA, {"registro": registros.SO + chave})

    assert _tipos(com_itens) == {Produto, VarianteProduto}
    assert _tipos(so_ele) == {Produto}
    pagina = com_itens.content.decode()
    assert "Armario e itens relacionados" in pagina and "Somente Produto: Armario" in pagina


def test_alvo_nao_inclui_registro_que_so_aponta_para_o_produto(conta):
    """Avaliacao/pedido apontam para o produto mas tem dono proprio (PROTECT/SET_NULL)."""
    produto = criar_produto("Mesa", sku="MESA-1")
    alvo = registros.alvo(registros.chave(produto))
    modelos = {ContentType.objects.get_for_id(tipo).model for tipo in alvo}
    assert modelos == {"produto", "varianteproduto"}


def test_tela_do_log_mostra_rotulo_nome_do_usuario_e_requisicao(admin_logado, conta):
    """"Alterado por: None -> 2" virava "Alterado por: - -> maria (#2)" e o log diz quem fez."""
    produto = criar_produto("Cadeira", sku="CAD-1")
    maria = User.objects.create_user("maria", "maria@loja.test", "senha-forte-123",
                                     account=conta)
    with tenant_context(conta, maria):
        produto.nome = "Cadeira gamer"
        produto.save()
    log = LogEntry.objects.get_for_object(produto).filter(action=LogEntry.Action.UPDATE).first()

    pagina = admin_logado.get(f"{LISTA}{log.pk}/change/").content.decode()

    assert log.actor == maria
    assert "Alterado por" in pagina and f"maria (#{maria.pk})" in pagina
    assert "maria &lt;maria@loja.test&gt;" in pagina  # card "Quem fez"
    assert "Cadeira gamer" in pagina and "Registro completo" in pagina
    assert "&gt;None&lt;" not in pagina and "Field" not in pagina
    # O retrato guarda o registro inteiro, menos credencial.
    assert log.serialized_data["fields"]["nome"] == "Cadeira gamer"


def test_requisicao_vai_no_log_e_um_id_junta_o_que_ela_alterou(conta):
    """Sem metodo/caminho/IP e sem correlacao, o log nao dizia de qual chamada veio."""
    produto = criar_produto("Banco", sku="BAN-1")
    url = f"/admin/loja/produto/{produto.pk}/change/"
    pedido = SimpleNamespace(method="POST", path=url, META={"REMOTE_ADDR": "10.0.0.9"})

    with origem("admin", requisicao=requisicao_de(pedido)):
        produto.nome = "Banco alto"
        produto.save()
        variante = produto.variante_padrao
        variante.sku = "BAN-1-ALTO"
        variante.save()

    logs = LogEntry.objects.filter(additional_data__requisicao__caminho=url)
    assert logs.count() == 2
    assert logs.first().additional_data["requisicao"] == {
        "metodo": "POST", "caminho": url, "ip": "10.0.0.9"}
    assert len({log.cid for log in logs}) == 1 and logs.first().cid


def test_versao_do_historico_nao_vira_log(conta):
    """Logar a tabela do historico dobrava cada log (metade da lista era copia)."""
    criar_produto("Puff", sku="PUF-1")
    modelos = {log.content_type.model for log in LogEntry.objects.all()}
    assert not any(nome.startswith("historical") for nome in modelos)
