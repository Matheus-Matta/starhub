from io import BytesIO
from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import MidiaProduto, Produto
from apps.shopify.webhooks import processar_webhook

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class RespostaImagem(BytesIO):
    headers = {"Content-Length": str(len(PNG))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _configuracao(conta):
    matriz = permissoes.matriz_vazia()
    matriz["receber"]["produtos"]["create"] = True
    return ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=matriz
    )


def _produto_shopify():
    return {
        "id": 999,
        "title": "Produto com foto",
        "handle": "produto-com-foto",
        "variants": [{"sku": "FOTO-1", "price": "50.00"}],
        "images": [{
            "id": 123,
            "src": "https://cdn.shopify.com/s/files/1/produto.png?v=1",
            "alt": "Produto de frente",
        }],
    }


@pytest.mark.django_db
@pytest.mark.parametrize("operacao", ["create", "update"])
def test_create_e_update_inexistente_baixam_imagens(operacao, conta, settings, tmp_path):
    """Produto criado por qualquer evento precisa ter galeria local, nao URL remota."""
    settings.MEDIA_ROOT = tmp_path
    configuracao = _configuracao(conta)

    with patch("urllib.request.urlopen", return_value=RespostaImagem(PNG)):
        processar_webhook(
            configuracao, "produtos", operacao, _produto_shopify(), lambda *_: None
        )

    produto = Produto.objects.get()
    midia = MidiaProduto.objects.get(produto=produto)
    assert midia.url.startswith("/media/produtos/")
    assert midia.alt_text == "Produto de frente"
    vinculo = ExternalReference.objects.get(entity_type="midias", object_id=str(midia.pk))
    assert vinculo.external_id == "gid://shopify/ProductImage/123"
    assert vinculo.metadata == {"shopify_src": "https://cdn.shopify.com/s/files/1/produto.png?v=1"}
    assert (tmp_path / midia.url.removeprefix("/media/")).exists()


@pytest.mark.django_db
def test_update_nao_baixa_novamente_imagem_shopify_inalterada(conta, settings, tmp_path):
    """Webhook repetido nao pode duplicar midia nem trafego para o CDN."""
    settings.MEDIA_ROOT = tmp_path
    configuracao = _configuracao(conta)
    dados = _produto_shopify()

    with patch("urllib.request.urlopen", return_value=RespostaImagem(PNG)) as baixar:
        processar_webhook(configuracao, "produtos", "create", dados, lambda *_: None)
        processar_webhook(configuracao, "produtos", "update", dados, lambda *_: None)

    assert baixar.call_count == 1
    assert MidiaProduto.objects.count() == 1
