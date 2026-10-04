"""Envio de avaliacao pelo tema: o token assinado no Liquid diz quem e o cliente."""

import time
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Avaliacao, Cliente
from apps.loja.services.variantes import criar_produto
from apps.shopify.avaliacoes_token import TokenInvalido, assinar, conferir

SEGREDO = "segredo-do-tema-123"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpo(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    cache.clear()  # o limite de envios por IP fica no cache entre os testes


@pytest.fixture
def loja(conta):
    config = ConfiguracaoIntegracao(account=conta, dominio_loja="loja.myshopify.com")
    config.segredo_avaliacoes = SEGREDO
    config.save()
    produto = criar_produto("Poltrona", sku="POL-1", price=Decimal("10.00"))
    cliente = Cliente.objects.create(email="ana@x.com", nome="Ana", sobrenome="Lima")
    for entidade, obj, gid in (("produtos", produto, "gid://shopify/Product/55"),
                               ("clientes", cliente, "gid://shopify/Customer/77")):
        ExternalReference.objects.create(platform="shopify", entity_type=entidade,
                                         object_id=str(obj.pk), external_id=gid)
    return config, produto, cliente


def _token(cliente="77", produto="55", carimbo=None, segredo=SEGREDO):
    payload = f"{cliente}:{produto}:{int(carimbo or time.time())}"
    return {"payload": payload, "sig": assinar(segredo, payload)}


def _url(config):
    return f"/integracoes/shopify/avaliacoes/{config.pk}/"


def _enviar(client, config, **dados):
    corpo = {**_token(), "nota": "5", "comentario": "Linda e confortavel", **dados}
    return client.post(_url(config), corpo)


def test_token_assinado_pelo_liquid_e_aceito():
    """hmac_sha256 do Liquid sai em hex minusculo; o hub tem que bater exatamente."""
    token = _token()
    assert conferir(SEGREDO, token["payload"], token["sig"].upper()) == ("77", "55")


@pytest.mark.parametrize("token,motivo", [
    (_token(segredo="outro"), "Assinatura"),
    (_token(carimbo=time.time() - 3 * 3600), "expirou"),
    (_token(carimbo=time.time() + 3600), "expirou"),
    ({"payload": "77:55", "sig": assinar(SEGREDO, "77:55")}, "formato"),
])
def test_token_falso_velho_ou_torto_e_recusado(token, motivo):
    with pytest.raises(TokenInvalido, match=motivo):
        conferir(SEGREDO, token["payload"], token["sig"])


def test_sem_segredo_configurado_nada_passa():
    """Segredo vazio assinaria qualquer payload com a chave "": todo mundo passaria."""
    token = _token(segredo="")
    with pytest.raises(TokenInvalido, match="segredo"):
        conferir("", token["payload"], token["sig"])


def test_post_cria_avaliacao_pendente_do_cliente_do_token(client, loja):
    config, produto, cliente = loja
    foto = SimpleUploadedFile("a.png", PNG, content_type="image/png")
    resposta = _enviar(client, config, fotos=[foto])
    assert resposta.status_code == 201, resposta.json()
    avaliacao = Avaliacao.objects.get()
    assert (avaliacao.cliente, avaliacao.produto) == (cliente, produto)
    assert avaliacao.status == "pendente" and avaliacao.origin == "shopify"
    assert avaliacao.fotos.count() == 1
    assert resposta.json()["id"] == avaliacao.pk


def test_token_invalido_responde_401_sem_gravar(client, loja):
    config, _, _ = loja
    resposta = _enviar(client, config, sig="0" * 64)
    assert resposta.status_code == 401
    assert resposta.json()["erro"] == "token_invalido"
    assert not Avaliacao.objects.exists()


def test_segunda_avaliacao_responde_409_e_entrada_errada_400(client, loja):
    """409 e 400 separados: o tema que reenvia 400 corrigido nao pode reenviar o 409."""
    config, _, _ = loja
    assert _enviar(client, config, nota="9").status_code == 400
    assert _enviar(client, config).status_code == 201
    repetida = _enviar(client, config)
    assert repetida.status_code == 409
    assert repetida.json()["erro"] == "avaliacao_existente"


def test_cliente_que_o_hub_nao_conhece_responde_409(client, loja):
    config, _, _ = loja
    payload = _token(cliente="999")
    resposta = _enviar(client, config, **payload)
    assert resposta.status_code == 409
    assert resposta.json()["erro"] == "cliente_nao_sincronizado"


def test_produto_desconhecido_responde_404(client, loja):
    config, _, _ = loja
    assert _enviar(client, config, **_token(produto="1")).status_code == 404


def test_avaliacao_cai_na_conta_da_loja_do_endereco(client, loja, outra_conta):
    """O endereco tem o id da loja: avaliacao nao pode vazar para a conta de outra loja."""
    config, _, _ = loja
    _enviar(client, config)
    assert Avaliacao.all_objects.get().account_id == config.account_id


def test_get_diz_se_o_cliente_ja_avaliou(client, loja):
    config, _, _ = loja
    assert client.get(_url(config), _token()).json() == {"avaliou": False, "status": None}
    _enviar(client, config)
    assert client.get(_url(config), _token()).json() == {"avaliou": True, "status": "pendente"}


def test_rejeitada_nao_conta_como_ja_avaliou(client, loja):
    """Rejeitada: o tema volta a mostrar o formulario e o novo envio passa."""
    config, _, _ = loja
    _enviar(client, config)
    Avaliacao.objects.update(status=Avaliacao.Status.REJEITADA)
    assert client.get(_url(config), _token()).json() == {"avaliou": False, "status": None}
    assert _enviar(client, config).status_code == 201
    assert client.get(_url(config), _token()).json() == {"avaliou": True, "status": "pendente"}


def test_envios_alem_do_limite_respondem_429(client, loja, monkeypatch):
    # A taxa e lida uma vez na classe do DRF; monkeypatch devolve a original no fim
    # (trocar settings deixava o login JWT dos outros testes sem taxa).
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"avaliacoes": "2/hour"})
    config, _, _ = loja
    codigos = [_enviar(client, config, nota="0").status_code for _ in range(3)]
    assert codigos == [400, 400, 429]
