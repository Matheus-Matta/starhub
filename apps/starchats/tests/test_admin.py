import pytest
from django.apps import apps
from django.conf import settings
from django.urls import reverse

from apps.starchats.models import ConfiguracaoStarChats, ModeloMensagem

pytestmark = pytest.mark.django_db


def test_menu_separa_integracao_de_cadastros_genericos():
    """StarChats e uma conexao; modelos e regras pertencem a Mensagens."""
    assert apps.get_app_config("starchats").verbose_name == "Mensagens"
    assert settings.STARHUB_MENU_AGRUPAR["starchats.configuracaostarchats"] == (
        "integracoes"
    )
    assert ConfiguracaoStarChats._meta.verbose_name_plural == "StarChats"


def test_modelo_identifica_a_plataforma_de_mensagens(conta):
    """Outro provedor deve poder usar o cadastro comum sem fingir ser StarChats."""
    campo = ModeloMensagem._meta.get_field("plataforma")
    modelo = ModeloMensagem.objects.create(
        account=conta,
        plataforma="outro_provedor",
        caixa_entrada_id=81,
        nome="pedido_pronto",
        idioma="pt_BR",
    )

    assert campo.verbose_name == "plataforma de mensagens"
    assert campo.default == "starchats"
    assert modelo.configuracao_id is None


def test_configuracao_fica_no_admin_com_nome_starchats(admin_logado):
    """A marca tecnica da API nao deve substituir o nome StarChats na interface."""
    resposta = admin_logado.get(
        reverse("admin:starchats_configuracaostarchats_changelist"), follow=True
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "StarChats" in html
    assert "Integracoes" in html
    assert "Token de acesso" in html
    assert "Caixa do WhatsApp oficial" in html


def test_admin_salva_token_sem_reexibir_e_agenda_sincronizacao(
    admin_logado, conta, monkeypatch
):
    """Salvar credenciais agenda a busca, mas nunca devolve o segredo no HTML."""
    chamadas = []
    monkeypatch.setattr(
        "apps.starchats.admin.enfileirar",
        lambda tarefa, *args: chamadas.append((tarefa.name, args)),
    )
    url = reverse("admin:starchats_configuracaostarchats_add")

    resposta = admin_logado.post(
        url,
        {
            "url_base": "https://chat.exemplo.com/",
            "conta_externa_id": "12",
            "account": str(conta.pk),
            "origin": "starhub",
            "token_acesso": "nao-mostrar-este-token",
            "caixa_entrada_id": "",
            "active": "on",
            "sincronizar_agora": "on",
            "_save": "Salvar",
        },
        follow=True,
    )

    configuracao = ConfiguracaoStarChats.objects.get()
    assert resposta.status_code == 200
    assert configuracao.url_base == "https://chat.exemplo.com"
    assert "nao-mostrar-este-token" not in resposta.content.decode()
    assert chamadas == [("apps.starchats.tasks.sincronizar_starchats", (str(conta.pk),))]
