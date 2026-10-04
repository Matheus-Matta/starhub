"""Importacao do Shopify com item com problema: status proprio e detalhe por item."""

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.contexto import avisar
from apps.shopify.tasks import sincronizar_shopify

COM_FALHAS = ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS


def _rodar(monkeypatch, funcao):
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
    )
    monkeypatch.setattr("apps.shopify.tasks.sincronizar_loja", funcao)
    resultado = sincronizar_shopify.run(str(execucao.pk))
    execucao.refresh_from_db()
    return resultado, execucao


@pytest.mark.django_db
def test_importacao_com_aviso_de_item_fica_concluida_com_falhas(monkeypatch):
    """Com aviso a tarefa saia "Concluida" e o problema ficava escondido no texto."""
    def sincronizar(_configuracao, _progresso):
        avisar("Codigo de barras 789 ja e de outra variante no hub; corrija na loja.",
               recurso="produtos", id="12", descricao="Camiseta (SKU CAM-1)",
               id_externo="gid://shopify/Product/9")
        return "10 itens encontrados; 2 novos cadastros."

    resultado, execucao = _rodar(monkeypatch, sincronizar)

    assert execucao.status == COM_FALHAS
    assert resultado["status"] == COM_FALHAS
    assert execucao.falhas == [{
        "recurso": "produtos", "id": "12", "descricao": "Camiseta (SKU CAM-1)",
        "id_externo": "gid://shopify/Product/9",
        "motivo": "Codigo de barras 789 ja e de outra variante no hub; corrija na loja.",
    }]
    assert execucao.mensagem.startswith("10 itens encontrados; 2 novos cadastros. 1 com falha")
    assert "veja a lista de falhas" in execucao.mensagem


@pytest.mark.django_db
def test_aviso_so_com_texto_continua_registrado_como_falha(monkeypatch):
    """Quem chama avisar(texto) sem identificar o item nao pode perder o aviso."""
    def sincronizar(_configuracao, _progresso):
        avisar("Imagem da colecao nao baixada (sala.png): timeout.")
        return "1 itens encontrados."

    _resultado, execucao = _rodar(monkeypatch, sincronizar)

    assert execucao.status == COM_FALHAS
    assert execucao.falhas[0]["motivo"] == "Imagem da colecao nao baixada (sala.png): timeout."
    assert execucao.falhas[0]["recurso"] == ""


@pytest.mark.django_db
def test_erro_que_derruba_a_sync_continua_falhou_e_guarda_os_avisos_anteriores(monkeypatch):
    """Erro geral e FALHOU; os avisos coletados antes dele sumiam junto com a mensagem."""
    def sincronizar(_configuracao, _progresso):
        avisar("Imagem nao baixada.", recurso="categorias", id="3")
        raise RuntimeError("Shopify respondeu HTTP 401: token invalido")

    resultado, execucao = _rodar(monkeypatch, sincronizar)

    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert resultado["status"] == "failed"
    assert [f["recurso"] for f in execucao.falhas] == ["categorias", ""]
    assert execucao.falhas[1]["motivo"].startswith("O marketplace recusou as credenciais")
    assert "token invalido" in execucao.mensagem
