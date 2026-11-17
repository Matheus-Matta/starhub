"""Botao "Historico": versoes de API/webhook/tarefa com autor e motivo, e reverter."""

import pytest
from django.contrib.auth.models import Permission

from apps.core.models import User
from apps.core.origem import origem
from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.models import Produto
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


def _historico(produto):
    return f"/admin/loja/produto/{produto.pk}/history/"


def _versao(obj, **filtro):
    return obj.historical.filter(**filtro).order_by("-history_date").first()


@pytest.fixture
def tarefa(conta):
    return ExecucaoIntegracao.objects.create(tipo=ExecucaoIntegracao.Tipo.RECEBER)


@pytest.fixture
def produto(conta, tarefa):
    produto = criar_produto("Sofa", sku="SOF-1")
    with origem("shopify", via="Loja Matriz", tarefa=tarefa.pk):
        produto.nome = "Sofa retratil"
        produto.save()
        variante = produto.variante_padrao
        variante.sku = "SOF-1-CINZA"
        variante.save()
    return produto


def test_versao_de_webhook_guarda_por_onde_veio(produto, tarefa):
    """Sem request o simple_history gravava a versao sem autor nem motivo."""
    versao = _versao(produto, nome="Sofa retratil")
    assert versao.history_change_reason == f"shopify - Loja Matriz - tarefa #{tarefa.pk}"


def test_historico_mostra_as_versoes_do_produto_e_da_variante(admin_logado, produto, tarefa):
    """O botao abria o historico do Django: so o que foi salvo pelo admin aparecia."""
    pagina = admin_logado.get(_historico(produto)).content.decode()

    assert f"shopify - Loja Matriz - tarefa #{tarefa.pk}" in pagina
    assert "Sofa retratil" in pagina and "SOF-1-CINZA" in pagina  # produto e variante
    assert f"ver tarefa #{tarefa.pk}" in pagina and "Reverter" in pagina
    so_produto = admin_logado.get(_historico(produto), {"so": "1"}).content.decode()
    assert "SOF-1-CINZA" not in so_produto


def test_reverter_mostra_o_que_muda_e_volta_o_valor(admin_logado, produto):
    original = _versao(produto, nome="Sofa", history_type="+")
    url = f"{_historico(produto)}{_tipo(Produto)}/{original.history_id}/reverter/"

    confirmacao = admin_logado.get(url).content.decode()
    assert "Sofa retratil" in confirmacao and "Vai ficar" in confirmacao
    assert Produto.objects.get(pk=produto.pk).nome == "Sofa retratil"  # GET nao grava

    assert admin_logado.post(url).status_code == 302
    produto.refresh_from_db()
    assert produto.nome == "Sofa"
    motivo = _versao(produto).history_change_reason
    assert motivo == f"revertido para a versao #{original.history_id}"


def test_versao_de_outro_registro_nao_abre_pelo_produto(admin_logado, produto):
    """O id da versao na URL nao pode reverter um registro que nao e deste produto."""
    outro = criar_produto("Mesa", sku="MES-1")
    versao = _versao(outro)
    url = f"{_historico(produto)}{_tipo(Produto)}/{versao.history_id}/reverter/"
    assert admin_logado.post(url).status_code == 404


def test_quem_so_ve_nao_reverte(client, conta, produto):
    leitor = User.objects.create_user("leitor", "l@loja.test", "senha-forte-123",
                                      account=conta, is_staff=True)
    leitor.user_permissions.set(Permission.objects.filter(codename="view_produto"))
    client.force_login(leitor)
    original = _versao(produto, history_type="+")

    pagina = client.get(_historico(produto)).content.decode()
    resposta = client.post(f"{_historico(produto)}{_tipo(Produto)}/{original.history_id}/reverter/")

    assert "Sofa retratil" in pagina and "Reverter" not in pagina
    assert resposta.status_code == 403


def _tipo(modelo):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(modelo).pk
