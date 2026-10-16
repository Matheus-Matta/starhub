import pytest
from django.urls import reverse

from apps.starchats.models import ConfiguracaoStarChats

pytestmark = pytest.mark.django_db


def test_configuracao_fica_no_admin_com_nome_starchats(admin_logado):
    """A marca tecnica da API nao deve substituir o nome StarChats na interface."""
    resposta = admin_logado.get(
        reverse("admin:starchats_configuracaostarchats_changelist"), follow=True
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "StarChats" in html
    assert "Token de acesso" in html


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
