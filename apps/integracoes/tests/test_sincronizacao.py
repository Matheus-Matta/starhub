from unittest.mock import Mock

import pytest
from django.db import IntegrityError, transaction

from apps.integracoes import sincronizacao
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.sincronizacao import (
    EXPORTAR,
    IMPORTAR,
    SincronizacaoEmAndamento,
    iniciar,
    recursos_disponiveis,
)

from .envio_falso import configuracao as config_falsa


def _config(receber=(), enviar=()):
    config = config_falsa("shopify", recursos=())
    matriz = config.permissoes
    for recurso in receber:
        matriz["receber"][recurso]["get"] = True
    for recurso, operacao in enviar:
        matriz["enviar"][recurso][operacao] = True
    config.permissoes = matriz
    config.save()
    return config


@pytest.fixture
def fila(monkeypatch):
    tarefas = {"importar": Mock(), "exportar": Mock()}
    for mock in tarefas.values():
        mock.delay.return_value.id = "celery-1"
    monkeypatch.setattr(
        sincronizacao, "_tarefa",
        lambda _config, direcao: tarefas[direcao],
    )
    return tarefas


def _por_recurso(itens):
    return {item["recurso"]: (item["permitido"], item["motivo"]) for item in itens}


@pytest.mark.django_db
def test_importar_so_libera_recurso_com_buscar_ligado(falsos):
    """Switch liberado sem Buscar ligado criaria tarefa que nao busca nada."""
    config = _config(receber=["produtos"])

    itens = _por_recurso(recursos_disponiveis(config, IMPORTAR))

    assert itens["produtos"] == (True, "")
    assert itens["pedidos"] == (False, "Ligue Receber > Pedidos > Buscar")


@pytest.mark.django_db
def test_exportar_libera_com_criar_ou_atualizar_e_exige_enviador(falsos):
    """Exportar sem enviador do recurso so geraria 'ignorado' para cada registro."""
    config = _config(
        enviar=[("produtos", "update"), ("categorias", "create"), ("cupons", "create")]
    )

    itens = _por_recurso(recursos_disponiveis(config, EXPORTAR))

    assert itens["produtos"] == (True, "")
    assert itens["categorias"] == (True, "")
    assert itens["estoque"] == (False, "Ligue Enviar > Estoque > Criar ou Atualizar")
    assert itens["cupons"][0] is False  # o falso nao tem enviador de cupons
    assert "ainda nao existe" in itens["cupons"][1]


@pytest.mark.django_db(transaction=True)
def test_iniciar_cria_com_parametros_e_enfileira_depois_do_commit(falsos, fila, conta):
    """Enfileirar antes do commit deixa o worker procurar uma execucao que nao existe."""
    config = _config(receber=["produtos", "clientes"])

    with transaction.atomic():
        execucao = iniciar(config, IMPORTAR, ["clientes", "produtos", "produtos"])
        assert not fila["importar"].delay.called

    fila["importar"].delay.assert_called_once_with(str(execucao.pk))
    execucao.refresh_from_db()
    assert execucao.tipo == ExecucaoIntegracao.Tipo.SINCRONIZAR
    assert execucao.parametros == {"direcao": "importar", "recursos": ["produtos", "clientes"]}
    assert execucao.celery_task_id == "celery-1"


@pytest.mark.django_db
@pytest.mark.parametrize(("direcao", "recursos", "trecho"), [
    ("ambos", ["produtos"], "Escolha a direcao"),
    (IMPORTAR, [], "ao menos um"),
    (IMPORTAR, ["frete"], "desconhecido: frete"),
    (IMPORTAR, ["pedidos"], "Ligue Receber > Pedidos > Buscar"),
])
def test_iniciar_recusa_entrada_errada_com_mensagem_para_o_operador(
    falsos, fila, direcao, recursos, trecho
):
    """Recurso bloqueado passando pela tela criaria tarefa que a configuracao proibe."""
    config = _config(receber=["produtos"])

    with pytest.raises(ValueError, match=trecho):
        iniciar(config, direcao, recursos)

    assert not ExecucaoIntegracao.objects.exists()


@pytest.mark.django_db
def test_segunda_sincronizacao_devolve_a_que_esta_rodando(falsos, fila):
    """Duas sincronizacoes da mesma loja gravam o mesmo registro em paralelo."""
    config = _config(receber=["produtos"], enviar=[("produtos", "create")])
    primeira = iniciar(config, IMPORTAR, ["produtos"])

    with pytest.raises(SincronizacaoEmAndamento) as erro:
        iniciar(config, EXPORTAR, ["produtos"])

    assert erro.value.execucao == primeira


@pytest.mark.django_db
def test_indice_do_banco_segura_mesmo_quando_a_consulta_nao_ve_a_outra(
    falsos, fila, monkeypatch
):
    """O `if` roda antes do commit do outro clique; so o banco impede a duplicada."""
    config = _config(receber=["produtos"])
    primeira = iniciar(config, IMPORTAR, ["produtos"])
    original = sincronizacao.em_andamento
    chamadas = []

    def cega_na_primeira(config):
        chamadas.append(config)
        return None if len(chamadas) == 1 else original(config)

    monkeypatch.setattr(sincronizacao, "em_andamento", cega_na_primeira)

    with pytest.raises(SincronizacaoEmAndamento) as erro:
        iniciar(config, IMPORTAR, ["produtos"])

    assert erro.value.execucao == primeira
    assert len(chamadas) == 2  # a consulta nao viu; quem segurou foi o indice
    assert ExecucaoIntegracao.objects.count() == 1


@pytest.mark.django_db
def test_indice_permite_nova_depois_que_a_anterior_termina(falsos, fila):
    """Tarefa concluida ou com falha nao pode travar a loja para sempre."""
    config = _config(receber=["produtos"])
    primeira = iniciar(config, IMPORTAR, ["produtos"])
    ExecucaoIntegracao.objects.filter(pk=primeira.pk).update(status="failed")

    assert iniciar(config, IMPORTAR, ["produtos"]).pk != primeira.pk


@pytest.mark.django_db
def test_indice_nao_segura_envio_nem_webhook(falsos):
    """Envio de alteracao e webhook correm em paralelo a sincronizacao por desenho."""
    config = _config()
    for tipo in ("sync", "send", "send", "receive", "receive"):
        ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo)

    with pytest.raises(IntegrityError), transaction.atomic():
        ExecucaoIntegracao.objects.create(configuracao=config, tipo="export")


@pytest.mark.django_db(transaction=True)
def test_broker_fora_marca_falha_e_libera_a_loja(falsos, fila, conta):
    """Pendente que nunca entrou na fila travaria o indice e a loja nao sincronizaria mais."""
    config = _config(receber=["produtos"])
    fila["importar"].delay.side_effect = ConnectionError("redis fora")

    execucao = iniciar(config, IMPORTAR, ["produtos"])

    execucao.refresh_from_db()
    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert "Redis/Celery" in execucao.mensagem
    assert sincronizacao.em_andamento(config) is None
