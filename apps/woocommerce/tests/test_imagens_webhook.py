"""Imagens recebidas nos webhooks de produto do WooCommerce."""

from io import BytesIO
from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import configuracao
from apps.woocommerce.webhooks import processar_webhook

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
RECEBE_PRODUTOS = (("produtos", "create"), ("produtos", "update"))


class RespostaImagem(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


@pytest.mark.django_db
@pytest.mark.parametrize("operacao", ["create", "update"])
def test_criar_e_atualizar_produto_baixam_a_imagem(
        operacao, conta, settings, tmp_path):
    """A galeria do webhook precisa virar arquivo local, inclusive no update."""
    settings.MEDIA_ROOT = tmp_path
    cfg = configuracao(conta, receber=RECEBE_PRODUTOS)
    if operacao == "update":
        processar_webhook(cfg, "produtos", "create", exemplos.produto_simples(),
                          lambda *_: None)
    dados = exemplos.produto_simples(images=[{
        "id": 31, "src": "https://loja.exemplo.test/foto.png", "alt": "Sofá de frente",
    }])

    with (patch("apps.core.imagens_remotas._publico", return_value=True),
          patch("urllib.request.urlopen", return_value=RespostaImagem(PNG))):
        processar_webhook(cfg, "produtos", operacao, dados, lambda *_: None)

    midia = MidiaProduto.objects.get()
    assert midia.url.startswith("/media/produtos/")
    assert midia.alt_text == "Sofá de frente"
    assert (tmp_path / midia.url.removeprefix("/media/")).exists()
    vinculo = ExternalReference.objects.get(entity_type="midias", object_id=str(midia.pk))
    assert vinculo.external_id == "31"
