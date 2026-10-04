from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry

from apps.core import origem
from apps.core.models import ExternalReference
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.tasks import deve_repetir, enviar_alteracao
from apps.loja.models import Categoria, Produto

from .envio_falso import ApiFora, ProdutoFalso, configuracao


def _enviar(config, recurso, operacao, pk, **extras):
    return enviar_alteracao.run(str(config.pk), recurso, operacao, str(pk), **extras)


def _rastro():
    return ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.ENVIAR)


@pytest.mark.django_db
def test_tarefa_cria_vincula_e_grava_o_rastro(falsos):
    """Sem vinculo gravado, o proximo envio criaria o produto de novo no marketplace."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Camiseta")

    _enviar(config, "produtos", "create", produto.pk)
    _enviar(config, "produtos", "update", produto.pk)

    assert falsos == [("falso", "criar", produto.pk), ("falso", "atualizar", f"falso-{produto.pk}")]
    mensagens = list(ExecucaoIntegracao.objects.order_by("created_at").values_list(
        "status", "mensagem"
    ))
    assert mensagens == [
        ("completed", f"produtos create {produto.pk}: criado falso-{produto.pk}"),
        ("completed", f"produtos update {produto.pk}: atualizado"),
    ]


@pytest.mark.django_db
def test_update_sem_vinculo_com_criar_desligado_e_ignorado(falsos):
    """Editar produto que o marketplace nao conhece criava la sem o lojista ligar 'criar'."""
    config = configuracao("falso", recursos=())
    config.permissoes = {"enviar": {"produtos": {"update": True}}}
    config.save()
    produto = Produto.objects.create(nome="Camiseta")

    _enviar(config, "produtos", "update", produto.pk)

    assert falsos == []
    assert "criar' esta desligado" in _rastro().mensagem


@pytest.mark.django_db
def test_operacao_nao_suportada_fica_como_ignorada_e_nao_como_falha(falsos):
    """Categoria que o marketplace nao cria nao e erro: nao pode ir para a lista de falhas."""
    config = configuracao("falso")
    categoria = Categoria.objects.create(nome="Verao", slug="verao")

    resultado = _enviar(config, "categorias", "create", categoria.pk)

    rastro = _rastro()
    assert resultado["status"] == "completed"
    assert rastro.status == ExecucaoIntegracao.Status.CONCLUIDA
    assert "ignorado: falso nao cria categorias" in rastro.mensagem


@pytest.mark.django_db
def test_excluir_apaga_no_marketplace_e_desfaz_o_vinculo(falsos):
    """Vinculo orfao faria o proximo envio atualizar um id que nao existe mais."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Camiseta")
    _enviar(config, "produtos", "create", produto.pk)
    pk = produto.pk
    produto.delete()

    _enviar(config, "produtos", "delete", pk)

    assert falsos[-1] == ("falso", "excluir", f"falso-{pk}")
    assert not ExternalReference.objects.filter(platform="falso", object_id=str(pk)).exists()


@pytest.mark.django_db
def test_tarefa_roda_com_a_origem_do_destino(falsos, monkeypatch):
    """O que o envio grava no hub nao pode voltar para o mesmo marketplace (laco)."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Camiseta")
    vista = []
    def criar(self, obj):
        vista.append(origem.atual())
        return "x"

    monkeypatch.setattr(ProdutoFalso, "criar", criar)

    _enviar(config, "produtos", "create", produto.pk)

    assert vista == ["falso"]


@pytest.mark.django_db
def test_erro_da_api_sem_worker_marca_falha_com_a_mensagem(falsos, monkeypatch):
    """Falha do marketplace tem que aparecer na lista de tarefas, nao sumir no worker."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Camiseta")
    monkeypatch.setattr(ProdutoFalso, "criar", Mock(side_effect=ApiFora("503 do marketplace")))

    resultado = _enviar(config, "produtos", "create", produto.pk)

    assert resultado["status"] == "failed"
    rastro = _rastro()
    assert rastro.status == ExecucaoIntegracao.Status.FALHOU
    assert "503 do marketplace" in rastro.mensagem


@pytest.mark.django_db
def test_erro_da_api_no_worker_agenda_nova_tentativa_no_mesmo_rastro(falsos, monkeypatch):
    """Cada tentativa criando um rastro novo enchia a lista de tarefas com o mesmo envio."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Camiseta")
    monkeypatch.setattr(ProdutoFalso, "criar", Mock(side_effect=ApiFora("timeout")))
    monkeypatch.setattr("apps.integracoes.tasks.deve_repetir", lambda request: True)
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(enviar_alteracao, "retry", retry)

    with pytest.raises(Retry):
        _enviar(config, "produtos", "create", produto.pk)
    execucao_id = retry.call_args.kwargs["kwargs"]["execucao_id"]
    monkeypatch.setattr("apps.integracoes.tasks.deve_repetir", lambda request: False)
    _enviar(config, "produtos", "create", produto.pk, execucao_id=execucao_id)

    rastro = _rastro()
    assert str(rastro.pk) == execucao_id
    assert rastro.status == ExecucaoIntegracao.Status.FALHOU


def test_repete_so_no_worker_e_ate_tres_vezes():
    """Repetir no modo eager (dev) travava a tela do admin esperando o marketplace."""
    worker = {"called_directly": False, "is_eager": False}

    assert deve_repetir(SimpleNamespace(**worker, retries=0))
    assert not deve_repetir(SimpleNamespace(**worker, retries=3))
    assert not deve_repetir(SimpleNamespace(called_directly=False, is_eager=True, retries=0))
