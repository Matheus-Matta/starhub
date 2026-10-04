import pytest
from django.urls import reverse

from apps.integracoes.models import ExecucaoIntegracao

from .envio_falso import configuracao as config_falsa

LISTA = "admin:integracoes_execucaointegracao_changelist"


@pytest.fixture
def execucoes(db):
    config = config_falsa("shopify", recursos=("produtos",))
    tipo = ExecucaoIntegracao.Tipo.SINCRONIZAR
    # So uma tarefa de sincronizar pode estar em andamento por loja (indice unico).
    concluida = ExecucaoIntegracao.Status.CONCLUIDA
    return [
        ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo, status=concluida),
        ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo, status=concluida),
    ]


def test_lista_mostra_o_id_com_link_para_a_tarefa(admin_logado, execucoes):
    """Sem o id o operador nao consegue citar a tarefa ao pedir ajuda."""
    alvo = execucoes[0]
    html = admin_logado.get(reverse(LISTA)).content.decode()
    link = reverse("admin:integracoes_execucaointegracao_change", args=[alvo.pk])
    assert f'<a href="{link}">#{alvo.pk}</a>' in html
    assert html.index("field-id_fmt") < html.index("field-created_at")


@pytest.mark.parametrize("formato", ["{}", "#{}"])
def test_busca_pelo_id_com_ou_sem_cerquilha(admin_logado, execucoes, formato):
    """O operador copia '#779' da tela; a busca tem que aceitar do jeito que ele digita."""
    alvo, outra = execucoes
    resposta = admin_logado.get(reverse(LISTA), {"q": formato.format(alvo.pk)})
    achadas = list(resposta.context["cl"].result_list)
    assert alvo in achadas and outra not in achadas


def test_pagina_da_tarefa_traz_o_id_no_titulo(admin_logado, execucoes):
    """O titulo e o que aparece na aba do navegador e no cabecalho."""
    alvo = execucoes[0]
    url = reverse("admin:integracoes_execucaointegracao_change", args=[alvo.pk])
    html = admin_logado.get(url).content.decode()
    assert f"Tarefa #{alvo.pk} - Sincronizar loja" in html
