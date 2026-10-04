"""Moderacao no admin: aprovar/rejeitar leva a mudanca para a loja pelo envio."""

from decimal import Decimal

import pytest

from apps.integracoes import permissoes
from apps.integracoes.envio import distribuidor
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Avaliacao, Cliente
from apps.loja.services.avaliacoes import criar_avaliacao
from apps.loja.services.variantes import criar_produto

URL = "/admin/loja/avaliacao/"


@pytest.fixture
def enviados(monkeypatch, conta):
    matriz = permissoes.matriz_vazia()
    matriz["enviar"]["avaliacoes"] = {"get": False, "create": True, "update": True,
                                      "delete": True}
    ConfiguracaoIntegracao.objects.create(account=conta, permissoes=matriz)
    fila = []
    monkeypatch.setattr(distribuidor, "_enfileirar", lambda *args: fila.append(args[1:]))
    return fila


@pytest.fixture
def avaliacao(db):
    produto = criar_produto("Poltrona", sku="POL-1", price=Decimal("10.00"))
    cliente = Cliente.objects.create(email="ana@x.com", nome="Ana")
    return criar_avaliacao(cliente=cliente, produto=produto, nota=4, comentario="Boa")


def test_listagem_e_edicao_abrem(admin_logado, avaliacao):
    assert admin_logado.get(URL).status_code == 200
    assert admin_logado.get(f"{URL}{avaliacao.pk}/change/").status_code == 200


def test_avaliacao_nao_e_criada_pelo_admin(admin_logado):
    """Criada no admin, a avaliacao nao teria cliente real nem compra para conferir."""
    assert admin_logado.get(f"{URL}add/").status_code == 403


def test_acao_aprovar_grava_moderador_e_agenda_envio(
        admin_logado, avaliacao, enviados, django_capture_on_commit_callbacks):
    """Aprovar com update() nao dispararia o signal e a avaliacao nunca chegaria a loja."""
    with django_capture_on_commit_callbacks(execute=True):
        resposta = admin_logado.post(URL, {"action": "aprovar", "_selected_action": [avaliacao.pk]})
    assert resposta.status_code == 302
    aprovada = Avaliacao.objects.get(pk=avaliacao.pk)
    assert aprovada.status == "aprovada"
    assert aprovada.moderado_por.username == "admin"
    assert ("avaliacoes", "update", str(avaliacao.pk)) in enviados


def _moderar(cliente, avaliacao, **dados):
    return cliente.post(f"{URL}{avaliacao.pk}/moderar/", dados)


def test_botao_aprovar_aprova_e_agenda_o_envio(admin_logado, avaliacao, enviados,
                                              django_capture_on_commit_callbacks):
    """Um clique no Aprovar tem que levar a avaliacao para a loja, como a acao em lote."""
    with django_capture_on_commit_callbacks(execute=True):
        resposta = _moderar(admin_logado, avaliacao, acao="aprovar")
    assert resposta.status_code == 302
    assert resposta.url == f"{URL}{avaliacao.pk}/change/"
    aprovada = Avaliacao.objects.get(pk=avaliacao.pk)
    assert aprovada.status == "aprovada" and aprovada.moderado_por.username == "admin"
    assert ("avaliacoes", "update", str(avaliacao.pk)) in enviados


def test_botao_rejeitar_guarda_o_motivo(admin_logado, avaliacao):
    _moderar(admin_logado, avaliacao, acao="rejeitar", motivo="  Fala de outro produto ")
    rejeitada = Avaliacao.objects.get(pk=avaliacao.pk)
    assert rejeitada.status == "rejeitada"
    assert rejeitada.motivo_rejeicao == "Fala de outro produto"


def test_seguir_para_a_proxima_pendente_mais_antiga(admin_logado, avaliacao):
    """Moderar em fila: depois do clique a tela abre a proxima, sem voltar para a lista."""
    produto = avaliacao.produto
    outra = criar_avaliacao(cliente=Cliente.objects.create(email="b@x.com"), produto=produto,
                            nota=3, comentario="Ok")
    resposta = _moderar(admin_logado, avaliacao, acao="aprovar", proxima="1")
    assert resposta.url == f"{URL}{outra.pk}/change/"
    # Sem pendente sobrando, fica na mesma avaliacao.
    resposta = _moderar(admin_logado, outra, acao="aprovar", proxima="1")
    assert resposta.url == f"{URL}{outra.pk}/change/"


def test_moderar_so_por_post_e_com_acao_conhecida(admin_logado, avaliacao):
    """GET mudando status deixaria um link (ou o prefetch do navegador) aprovar sozinho."""
    assert admin_logado.get(f"{URL}{avaliacao.pk}/moderar/?acao=aprovar").status_code == 405
    _moderar(admin_logado, avaliacao, acao="apagar")
    assert Avaliacao.objects.get(pk=avaliacao.pk).status == "pendente"


def test_tela_mostra_comentario_fotos_e_botoes(admin_logado, avaliacao):
    html = admin_logado.get(f"{URL}{avaliacao.pk}/change/").content.decode()
    assert "Boa" in html
    assert 'value="aprovar"' in html and 'value="rejeitar"' in html
    assert 'value="pendente"' not in html  # ja esta pendente


def test_tela_toca_o_video_da_avaliacao(admin_logado, settings, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = tmp_path
    produto = criar_produto("Poltrona", sku="POL-1", price=Decimal("10.00"))
    cliente = Cliente.objects.create(email="ana@x.com", nome="Ana")
    video = SimpleUploadedFile("v.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 32)
    avaliacao = criar_avaliacao(cliente=cliente, produto=produto, nota=4, comentario="Boa",
                                fotos=[video])
    html = admin_logado.get(f"{URL}{avaliacao.pk}/change/").content.decode()
    assert "<video" in html and ".mp4" in html
