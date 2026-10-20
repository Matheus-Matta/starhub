import pytest
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("plataforma", "nome", "url"),
    [
        ("woocommerce", "WooCommerce", "admin:integracoes_configuracaointegracao_woocommerce"),
        ("suri", "Suri Shop", "admin:integracoes_configuracaointegracao_suri"),
    ],
)
def test_modal_de_sincronizacao_usa_o_nome_da_plataforma(
    admin_logado, plataforma, nome, url
):
    """A tela copiada da Shopify nao pode citar Shopify nas outras integracoes."""
    ConfiguracaoIntegracao.objects.create(
        nome=nome,
        plataforma=plataforma,
        dominio_loja="https://loja.exemplo.com",
    )

    html = admin_logado.get(reverse(url)).content.decode()

    assert f"Traz os dados da loja {nome} para o StarHub." in html
    assert f"Envia os dados do StarHub para a loja {nome}." in html
    assert "loja Shopify" not in html
