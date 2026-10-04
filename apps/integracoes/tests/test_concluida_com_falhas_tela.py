"""Status "Concluida com falhas": conta como terminado e aparece legivel no admin."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.integracoes import sincronizacao
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.sincronizacao import IMPORTAR, iniciar, liberar_travada

from .envio_falso import configuracao as config_falsa

COM_FALHAS = ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
FALHA = {
    "recurso": "produtos", "id": "41", "descricao": "Camiseta <b>azul</b> (SKU CAM-1)",
    "id_externo": "gid://shopify/Product/9", "motivo": "422 titulo invalido",
}


@pytest.fixture
def config(falsos, monkeypatch):
    tarefa = Mock()
    tarefa.delay.return_value.id = "celery-1"
    monkeypatch.setattr(sincronizacao, "_tarefa", lambda _c, _d: tarefa)
    config = config_falsa("shopify", recursos=())
    matriz = config.permissoes
    matriz["receber"]["produtos"]["get"] = True
    config.permissoes = matriz
    config.save()
    return config


def _com_falhas(config, **campos):
    return ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR, status=COM_FALHAS,
        mensagem="10 itens encontrados. 1 com falha.", falhas=[FALHA], **campos,
    )


@pytest.mark.django_db
def test_concluida_com_falhas_nao_trava_a_proxima_sincronizacao(config):
    """Se contasse como aberta, o indice barraria toda sincronizacao nova da loja."""
    anterior = _com_falhas(config)

    nova = iniciar(config, IMPORTAR, ["produtos"])

    assert nova.pk != anterior.pk


@pytest.mark.django_db
def test_concluida_com_falhas_antiga_nao_e_liberada_como_travada(config):
    """Liberar trocaria o resultado real por "Interrompida: sem sinal do worker"."""
    anterior = _com_falhas(config)
    ExecucaoIntegracao.objects.filter(pk=anterior.pk).update(
        updated_at=timezone.now() - timedelta(hours=2)
    )

    assert liberar_travada(anterior, sem_sinal_antes_de=timezone.now()) is False
    anterior.refresh_from_db()
    assert anterior.status == COM_FALHAS


@pytest.mark.django_db
def test_lista_mostra_concluida_com_falhas_em_amarelo(admin_logado, config):
    """Verde igual a "Concluida" escondia que houve item com erro."""
    _com_falhas(config)

    html = admin_logado.get(reverse("admin:integracoes_execucaointegracao_changelist"))

    assert '<span class="badge badge-warning">Concluida com falhas</span>' in html.content.decode()


@pytest.mark.django_db
def test_tarefa_mostra_as_falhas_em_tabela_e_nao_json(admin_logado, config):
    """O operador precisa ver item, id externo e motivo, nao o JSON cru do campo."""
    execucao = _com_falhas(config)
    url = reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk])

    html = admin_logado.get(url).content.decode()

    assert 'class="table tabela-falhas"' in html
    assert "<td>Produtos</td>" in html
    assert "#41" in html and "gid://shopify/Product/9" in html
    assert "422 titulo invalido" in html
    assert "Camiseta &lt;b&gt;azul&lt;/b&gt;" in html, "descricao vem do marketplace: escapar"
    assert 'class="form-row field-falhas"' not in html, "o campo JSON cru nao aparece"


@pytest.mark.django_db
def test_tarefa_sem_falhas_mostra_traco(admin_logado, config):
    """Tabela vazia confunde: sem falha a linha diz so "-"."""
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
        status=ExecucaoIntegracao.Status.CONCLUIDA,
    )
    url = reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk])

    html = admin_logado.get(url).content.decode()

    assert "tabela-falhas" not in html
