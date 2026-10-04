import pytest

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.tasks import sincronizar_shopify


@pytest.mark.django_db
def test_tarefa_registra_inicio_progresso_e_conclusao(monkeypatch):
    """O acompanhamento precisa sobreviver ao processo do Celery e mostrar o resultado."""
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao,
        tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
    )

    def sincronizar(_configuracao, progresso):
        progresso(2, 5, "Produtos")
        return "3 itens sincronizados."

    monkeypatch.setattr("apps.shopify.tasks.sincronizar_loja", sincronizar)
    sincronizar_shopify.run(str(execucao.pk))

    execucao.refresh_from_db()
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA
    assert (execucao.processados, execucao.total, execucao.etapa) == (5, 5, "Concluida")
    assert execucao.mensagem == "3 itens sincronizados."


@pytest.mark.django_db
def test_tarefa_guarda_erro_sem_perder_o_acompanhamento(monkeypatch):
    """Falha da API precisa aparecer na lista de tarefas, nao sumir no worker."""
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao,
        tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
    )

    def falhar(_configuracao, _progresso):
        raise RuntimeError("Token recusado pelo Shopify")

    monkeypatch.setattr("apps.shopify.tasks.sincronizar_loja", falhar)
    sincronizar_shopify.run(str(execucao.pk))

    execucao.refresh_from_db()
    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert execucao.etapa == "Falhou"
    assert "Token recusado" in execucao.mensagem


@pytest.mark.django_db
def test_tarefa_passa_os_recursos_pedidos_na_tela(monkeypatch):
    """Sem ler os parametros a tarefa ignorava a escolha do operador e buscava tudo."""
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
        parametros={"direcao": "importar", "recursos": ["clientes"]},
    )
    recebidos = []

    def sincronizar(_configuracao, _progresso, recursos=None):
        recebidos.append(recursos)
        return "ok"

    monkeypatch.setattr("apps.shopify.tasks.sincronizar_loja", sincronizar)
    sincronizar_shopify.run(str(execucao.pk))

    assert recebidos == [["clientes"]]
