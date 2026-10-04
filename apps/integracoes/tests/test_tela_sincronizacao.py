from unittest.mock import Mock, patch

import pytest
from django.contrib.messages import get_messages
from django.template import Context, Template
from django.urls import reverse

from apps.integracoes import sincronizacao
from apps.integracoes.models import ExecucaoIntegracao

from .envio_falso import configuracao as config_falsa

URL = "admin:integracoes_configuracaointegracao_shopify"


def _config():
    config = config_falsa("shopify", recursos=("produtos",))
    matriz = config.permissoes
    matriz["receber"]["produtos"]["get"] = True
    config.permissoes = matriz
    config.save()
    return config


@pytest.fixture
def fila(monkeypatch, falsos):
    tarefa = Mock()
    tarefa.delay.return_value.id = "celery-1"
    monkeypatch.setattr(sincronizacao, "_tarefa", lambda _config, _direcao: tarefa)
    return tarefa


def _mensagens(resposta):
    return [(m.level_tag, str(m)) for m in get_messages(resposta.wsgi_request)]


@pytest.mark.django_db
def test_tela_renderiza_modal_com_as_duas_listas_e_trava_o_nao_permitido(admin_logado, falsos):
    """Sem as duas listas o JS nao teria o que mostrar ao trocar a direcao."""
    _config()
    html = admin_logado.get(reverse(URL)).content.decode()
    assert "<dialog" in html and "data-modal-etapas" in html
    assert 'name="direcao"' in html and 'value="importar"' in html and 'value="exportar"' in html
    assert 'data-lista-direcao="importar"' in html and 'data-lista-direcao="exportar"' in html
    assert "Ligue Receber &gt; Clientes &gt; Buscar" in html  # motivo do switch travado
    assert "modal-etapas.js" in html and "modal-etapas.css" in html


@pytest.mark.django_db
def test_post_cria_tarefa_e_leva_para_a_pagina_dela(admin_logado, fila):
    """O operador precisa cair na tarefa para acompanhar, nao na tela de config."""
    config = _config()
    resposta = admin_logado.post(
        reverse(URL), {"acao": "sincronizar", "direcao": "importar", "recursos": ["produtos"]}
    )
    execucao = ExecucaoIntegracao.objects.get(configuracao=config)
    assert resposta.status_code == 302
    assert resposta.url == reverse(
        "admin:integracoes_execucaointegracao_change", args=[execucao.pk]
    )
    assert execucao.parametros == {"direcao": "importar", "recursos": ["produtos"]}


@pytest.mark.django_db
def test_post_com_recurso_nao_permitido_mostra_o_erro_e_nao_cria(admin_logado, fila):
    """Switch travado burlado pelo POST nao pode virar tarefa."""
    config = _config()
    resposta = admin_logado.post(
        reverse(URL), {"acao": "sincronizar", "direcao": "importar", "recursos": ["clientes"]}
    )
    assert resposta.status_code == 302 and resposta.url == reverse(URL)
    assert not ExecucaoIntegracao.objects.filter(configuracao=config).exists()
    (nivel, texto), = _mensagens(resposta)
    assert nivel == "error" and "Clientes" in texto


@pytest.mark.django_db
def test_post_com_outra_em_andamento_avisa_com_link_da_existente(admin_logado, fila):
    """Sem o link o operador nao sabe qual tarefa esperar."""
    config = _config()
    existente = ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR
    )
    resposta = admin_logado.post(
        reverse(URL), {"acao": "sincronizar", "direcao": "importar", "recursos": ["produtos"]}
    )
    (nivel, texto), = _mensagens(resposta)
    assert nivel == "warning"
    assert reverse("admin:integracoes_execucaointegracao_change", args=[existente.pk]) in texto
    assert ExecucaoIntegracao.objects.filter(configuracao=config).count() == 1


@pytest.mark.django_db
def test_pagina_da_execucao_em_andamento_se_atualiza_e_mostra_parametros_legiveis(admin_logado):
    """JSON cru na tela e proibido; e sem o gancho a pagina ficaria parada."""
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=_config(), tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
        parametros={"direcao": "importar", "recursos": ["produtos", "clientes"]},
    )
    url = reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk])
    html = admin_logado.get(url).content.decode()
    assert "data-tarefa-progresso" in html
    assert "Importar" in html and "Produtos" in html and "Clientes" in html
    assert '"direcao"' not in html and "{&#x27;" not in html
    ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(status="completed")
    assert "data-tarefa-progresso" not in admin_logado.get(url).content.decode()


def test_componente_modal_etapas_renderiza_slots_e_indicador():
    """Outra tela usa o componente so com slots; o indicador vem dos titulos."""
    html = Template(
        '{% load starhub %}{% componente "modal_etapas" id="m1" titulo="Assistente" '
        'titulo_1="Um" titulo_2="Dois" concluir="Criar" %}'
        '{% slot "etapa_1" %}<p>corpo-um</p>{% endslot %}'
        '{% slot "etapa_2" %}<p>corpo-dois</p>{% endslot %}{% endcomponente %}'
    ).render(Context({}))
    assert 'id="m1"' in html and "corpo-um" in html and "corpo-dois" in html
    assert html.count("data-etapa-indicador") == 2 and "Criar" in html


@pytest.mark.django_db
def test_acao_marcar_como_falhou_libera_a_travada(admin_logado, monkeypatch):
    """Sem a acao, uma tarefa travada em processando bloquearia a loja para sempre."""
    chamadas = []
    monkeypatch.setattr(
        sincronizacao, "liberar_travada", lambda execucao, **_: chamadas.append(execucao.pk) or True
    )
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=_config(), tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR
    )
    resposta = admin_logado.post(
        reverse("admin:integracoes_execucaointegracao_changelist"),
        {"action": "marcar_como_falhou", "_selected_action": [str(execucao.pk)]},
    )
    assert resposta.status_code == 302 and chamadas == [execucao.pk]
    assert "falhou" in " ".join(texto for _, texto in _mensagens(resposta)).lower()


@pytest.mark.django_db
def test_acao_sincronizar_cria_execucao_e_dispara_celery(
    admin_logado, django_capture_on_commit_callbacks
):
    """O clique apenas enfileira; chamada ao Shopify nunca roda dentro da requisicao."""
    _config()
    dados = {"acao": "sincronizar", "direcao": "importar", "recursos": ["produtos"]}
    alvo = "apps.shopify.tasks.sincronizar_shopify.delay"
    with patch(alvo, return_value=Mock(id="celery-123")) as delay:
        with django_capture_on_commit_callbacks(execute=True):
            resposta = admin_logado.post(reverse(URL), dados)

    execucao = ExecucaoIntegracao.objects.get()
    assert resposta.url.endswith(f"/{execucao.pk}/change/")
    assert execucao.tipo == ExecucaoIntegracao.Tipo.SINCRONIZAR
    assert execucao.celery_task_id == "celery-123"
    delay.assert_called_once_with(str(execucao.pk))


def _operador(client, conta, codenames):
    """Usuario de staff com so as permissoes pedidas na integracao."""
    from django.contrib.auth.models import Permission

    from apps.core.models import User

    usuario = User.objects.create_user(
        "operador", "op@loja.test", "senha-forte-123", account=conta, is_staff=True
    )
    usuario.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    client.force_login(usuario)
    return client


def _botao_sincronizar(html):
    inicio = html.index("Sincronizar loja</button>")
    return html[html.rindex("<button", 0, inicio):inicio]


@pytest.mark.django_db
def test_sem_permissao_de_editar_botao_sincronizar_sai_desabilitado(client, conta, falsos):
    """Botao ativo sem o dialog na pagina fazia o clique nao acontecer, sem aviso."""
    _config()
    _operador(client, conta, ["view_configuracaointegracao"])
    html = client.get(reverse(URL)).content.decode()
    botao = _botao_sincronizar(html)
    assert "disabled" in botao and "Peca a um administrador" in botao
    assert "data-abrir-modal-etapas" not in botao
    # O <dialog> de confirmacao (confirmar.js) existe em toda pagina; o de sincronizar nao.
    assert 'id="modal-sincronizar"' not in html


@pytest.mark.django_db
def test_com_permissao_de_editar_botao_abre_o_modal_que_esta_na_pagina(client, conta, falsos):
    """Botao e dialog precisam aparecer juntos: o id do botao tem que existir na pagina."""
    _config()
    _operador(client, conta, ["view_configuracaointegracao", "change_configuracaointegracao"])
    html = client.get(reverse(URL)).content.decode()
    assert 'data-abrir-modal-etapas="modal-sincronizar"' in _botao_sincronizar(html)
    assert 'id="modal-sincronizar"' in html and "<dialog" in html
