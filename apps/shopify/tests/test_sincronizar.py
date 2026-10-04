import pytest

from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.shopify import sincronizar


def _configuracao(*habilitados):
    matriz = permissoes.matriz_vazia()
    for recurso, operacao in habilitados:
        matriz["receber"][recurso][operacao] = True
    return ConfiguracaoIntegracao(nome="Loja", plataforma="shopify", permissoes=matriz)


@pytest.mark.django_db
def test_sincronizacao_busca_apenas_recursos_com_get_habilitado(monkeypatch):
    """Desmarcar Buscar precisa impedir inclusive a chamada externa daquele recurso."""
    configuracao = _configuracao(("produtos", "get"), ("pedidos", "create"))
    configuracao.save()
    consultados = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return None

        def listar(self, recurso):
            consultados.append(recurso)
            return iter([{"id": "gid://shopify/Product/1"}])

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)
    monkeypatch.setitem(sincronizar.SINCRONIZADORES, "produtos", lambda dados: (dados, True))

    mensagem = sincronizar.sincronizar_loja(configuracao, lambda *_args: None)

    assert consultados == ["produtos"]
    assert mensagem == "1 itens encontrados; 1 novos cadastros."


@pytest.mark.django_db
def test_webhooks_sao_criados_so_para_eventos_de_recebimento_habilitados(monkeypatch):
    """Buscar nao cria webhook e operacao de envio tambem nao deve assinar evento."""
    configuracao = _configuracao(("produtos", "get"), ("produtos", "create"))
    configuracao.url_webhook = "https://hub.test/integracoes/shopify/webhook"
    configuracao.save()
    criados = []
    excluidos = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def listar_webhooks(self):
            return iter([])

        def excluir_webhook(self, webhook_id):
            excluidos.append(webhook_id)

        def cadastrar_webhook(self, topico, uri):
            criados.append((topico, uri))

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)
    mensagem = sincronizar.cadastrar_webhooks(configuracao, lambda *_args: None)

    assert criados == [(
        "PRODUCTS_CREATE",
        f"https://hub.test/integracoes/shopify/webhook/{configuracao.uuid}/produtos/",
    )]
    assert excluidos == []
    assert mensagem == "1 webhooks cadastrados."


@pytest.mark.django_db
def test_recadastro_remove_webhooks_dos_endpoints_antes_de_recriar(monkeypatch):
    """Repetir o cadastro nao pode falhar por existir assinatura no mesmo endereco."""
    configuracao = _configuracao(
        ("produtos", "create"), ("produtos", "update"), ("clientes", "create")
    )
    configuracao.url_webhook = "https://hub.test/integracoes/shopify/webhook"
    configuracao.save()
    chamadas = []
    # Um no endereco antigo (id) e outro no novo (uuid): os dois saem antes de recriar.
    antigo = f"{configuracao.url_webhook}/{configuracao.pk}"
    novo = f"{configuracao.url_webhook}/{configuracao.uuid}"

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def listar_webhooks(self):
            return iter([
                {"id": "webhook-produto-1", "uri": f"{antigo}/produtos/"},
                {"id": "webhook-produto-2", "uri": f"{novo}/produtos"},
                {"id": "webhook-outro", "uri": "https://outro.test/webhook/"},
            ])

        def excluir_webhook(self, webhook_id):
            chamadas.append(("excluir", webhook_id))

        def cadastrar_webhook(self, topico, uri):
            chamadas.append(("criar", topico, uri))

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)

    mensagem = sincronizar.cadastrar_webhooks(configuracao, lambda *_args: None)

    assert chamadas[:2] == [
        ("excluir", "webhook-produto-1"),
        ("excluir", "webhook-produto-2"),
    ]
    assert all(chamada[0] == "criar" and str(configuracao.uuid) in chamada[2]
               for chamada in chamadas[2:])
    assert len(chamadas[2:]) == 3
    assert mensagem == "2 webhooks removidos; 3 cadastrados."


@pytest.mark.django_db
def test_sincronizacao_busca_so_os_recursos_escolhidos_e_permitidos(monkeypatch):
    """Importar so clientes buscava a loja inteira; recurso desligado nao pode entrar."""
    configuracao = _configuracao(("produtos", "get"), ("clientes", "get"))
    configuracao.save()
    consultados = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return None

        def listar(self, recurso):
            consultados.append(recurso)
            return iter([])

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)

    sincronizar.sincronizar_loja(
        configuracao, lambda *_args: None, recursos=["clientes", "pedidos"]
    )

    assert consultados == ["clientes"]


@pytest.mark.django_db
def test_sincronizacao_longa_da_sinal_de_vida_a_cada_lote_de_itens(monkeypatch):
    """Recurso com milhares de itens ficava 30 min sem sinal e era liberado no meio."""
    configuracao = _configuracao(("produtos", "get"))
    configuracao.save()
    etapas = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return None

        def listar(self, _recurso):
            return iter([{"id": n} for n in range(2 * sincronizar.SINAL_A_CADA + 1)])

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)
    monkeypatch.setitem(sincronizar.SINCRONIZADORES, "produtos", lambda dados: (dados, False))

    sincronizar.sincronizar_loja(configuracao, lambda *args: etapas.append(args[2]))

    lote = sincronizar.SINAL_A_CADA
    assert f"Produtos: {lote} processados" in etapas
    assert f"Produtos: {2 * lote} processados" in etapas
