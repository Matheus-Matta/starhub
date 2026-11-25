"""A mesma foto nao entra nem sai em dobro, e o eco do envio nao mexe no hub."""

from types import SimpleNamespace

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto
from apps.loja.services.variantes import criar_produto
from apps.shopify.envio import produtos_midias
from apps.shopify.envio.produtos_midias_reserva import VALIDADE, reservadas
from apps.shopify.tests.test_imagens_dois_sentidos import (
    Loja,
    apagar_no_hub,
    cdn,
    da_loja,
    foto,
    gid,
    mesa_na_loja,  # noqa: F401 - fixture "mesa"
    urls,
)

pytestmark = pytest.mark.django_db
UUID = "0123456789abcdef0123456789abcdef"


def test_produto_excluido_e_importado_de_novo_traz_as_fotos(mesa):
    """A exclusao do produto inteiro nao marca as fotos como apagadas."""
    da_loja(mesa.variante, 1)
    mesa.produto.delete()
    novo = criar_produto("Mesa", sku="M1")
    Loja(1).webhook(novo, 1)
    assert urls(novo) == ["/media/baixada-1.png"]


def test_eco_repetido_nao_grava_nada(mesa):
    """Ordem e texto mudados no hub voltavam ao da loja a cada webhook."""
    midia = da_loja(mesa.variante, 1)
    loja = Loja(1)
    loja.webhook(mesa.produto, 1)
    midia.posicao, midia.alt_text = 7, "do hub"
    midia.save()
    antes = midia.historical.count()

    loja.webhook(mesa.produto, 1)

    midia.refresh_from_db()
    assert (midia.posicao, midia.alt_text) == (7, "do hub")
    assert midia.historical.count() == antes and loja.baixadas == []


def test_ordem_mudada_na_loja_chega_ao_hub(mesa):
    a, b = da_loja(mesa.variante, 1), da_loja(mesa.variante, 2)
    loja = Loja(1, 2)
    loja.webhook(mesa.produto, 1, 2)
    loja.webhook(mesa.produto, 2, 1)
    a.refresh_from_db(), b.refresh_from_db()
    assert (a.posicao, b.posicao) == (1, 0)


def test_webhook_que_chega_antes_do_vinculo_reconhece_pelo_nome_do_arquivo(mesa):
    """O eco chegou entre a resposta da loja e a gravacao do vinculo: baixava uma copia."""
    midia = MidiaProduto.objects.create(produto=mesa.produto, variante=mesa.variante,
                                        url=f"/media/produtos/{UUID}.png")
    loja = Loja(5)
    loja.webhook(mesa.produto, 5, url=lambda n: cdn(f"{UUID}_a1b2"))
    assert urls(mesa.produto) == [midia.url] and loja.baixadas == []
    assert ExternalReference.objects.get(external_id=gid(5)).object_id == str(midia.pk)


def test_dois_envios_juntos_mandam_a_foto_uma_vez(mesa):
    """Sem reserva, os dois viam a foto sem vinculo e a loja ficava com duas."""
    midia = foto(mesa.variante, 1)
    grupos = [("https://hub.test/1.png", [midia])]
    with reservadas(grupos) as primeiro, reservadas(grupos) as segundo:
        assert (len(primeiro), len(segundo)) == (1, 0)


def test_envio_que_falhou_devolve_a_reserva(mesa):
    midia = foto(mesa.variante, 1)
    grupos = [("https://hub.test/1.png", [midia])]
    with pytest.raises(ValueError), reservadas(grupos):
        raise ValueError
    with reservadas(grupos) as de_novo:
        assert len(de_novo) == 1


def test_apagada_no_hub_e_removida_da_loja_uma_vez(mesa):
    """Na segunda vez o fileDelete responderia que o arquivo nao existe e falharia o envio."""
    apagar_no_hub(mesa.variante, da_loja(mesa.variante, 1))
    chamadas = []
    enviador = SimpleNamespace(mutacao=lambda _q, v, _c: chamadas.append(v))
    for _ in range(2):
        produtos_midias.remover(enviador, mesa.produto, [gid(1)], [])
    assert chamadas == [{"fileIds": [gid(1)]}]
    loja = Loja(1)
    loja.webhook(mesa.produto, 1)
    assert urls(mesa.produto) == [], "a loja ainda lista por instantes a que apagou"


def test_reserva_de_worker_que_morreu_vence(mesa):
    """Sem vencimento a foto nunca mais iria para a loja."""
    midia = foto(mesa.variante, 1)
    grupos = [("https://hub.test/1.png", [midia])]
    with reservadas(grupos):
        reserva = ExternalReference.objects.get(external_id=f"pendente:{midia.pk}")
        ExternalReference.objects.filter(pk=reserva.pk).update(
            updated_at=reserva.updated_at - 2 * VALIDADE)
        with reservadas(grupos) as de_novo:
            assert len(de_novo) == 1


def test_outro_webhook_gravou_a_foto_enquanto_este_baixava(mesa):
    """Os dois viram a foto sem vinculo; o segundo a gravava de novo."""
    class Simultanea(Loja):
        def graphql(self, *args):
            da_loja(mesa.variante, 1)  # o outro webhook termina antes deste baixar
            return super().graphql(*args)

    Simultanea(1).webhook(mesa.produto, 1)
    assert urls(mesa.produto) == ["/media/1.png"]


def test_enviada_pelo_hub_e_trocada_na_loja_atualiza_no_hub(mesa):
    """Mesmo id, arquivo novo na CDN (recorte no Shopify): passava por eco e nunca vinha."""
    foto(mesa.variante, 1, enviado_src="/media/1.png", shopify_src=cdn(1))
    loja = Loja(1)
    loja.webhook(mesa.produto, 1, url=lambda n: cdn("recortada"))
    loja.webhook(mesa.produto, 1, url=lambda n: cdn("recortada"))
    assert urls(mesa.produto) == ["/media/baixada-1.png"] and len(loja.baixadas) == 1
