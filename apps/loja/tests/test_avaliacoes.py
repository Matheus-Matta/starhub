"""Regras da avaliacao de produto (apps/loja/services/avaliacoes.py)."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.loja.models import Avaliacao, Cliente, ItemPedido, Pedido
from apps.loja.services.avaliacoes import (
    AvaliacaoConflito,
    AvaliacaoInvalida,
    criar_avaliacao,
    moderar,
    nome_publico,
)
from apps.loja.services.variantes import criar_produto

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def produto():
    return criar_produto("Poltrona", sku="POL-1", price=Decimal("1499.90"))


@pytest.fixture
def cliente():
    return Cliente.objects.create(email="ana@x.com", nome="Ana Maria", sobrenome="Lima Souza")


def _foto(nome="a.png", conteudo=PNG):
    return SimpleUploadedFile(nome, conteudo, content_type="image/png")


def _criar(cliente, produto, **extra):
    dados = {"nota": 5, "comentario": "Muito boa", **extra}
    return criar_avaliacao(cliente=cliente, produto=produto, **dados)


def test_nome_publico_mostra_so_a_inicial_do_sobrenome(cliente):
    """O sobrenome inteiro na vitrine expoe o cliente; "Ana L." basta para dar confianca."""
    assert nome_publico(cliente) == "Ana L."
    assert nome_publico(Cliente(email="x@x.com")) == "Cliente"


def test_avaliacao_nasce_pendente_com_as_fotos_na_ordem(cliente, produto):
    avaliacao = _criar(cliente, produto, fotos=[_foto("1.png"), _foto("2.png")])
    assert avaliacao.status == Avaliacao.Status.PENDENTE
    assert avaliacao.nome_publico == "Ana L."
    assert [f.ordem for f in avaliacao.fotos.all()] == [0, 1]
    assert avaliacao.fotos.first().imagem.name.endswith(".png")


@pytest.mark.parametrize("nota", [0, 6, "", "cinco", None])
def test_nota_fora_de_1_a_5_e_entrada_invalida(cliente, produto, nota):
    with pytest.raises(AvaliacaoInvalida) as erro:
        _criar(cliente, produto, nota=nota)
    assert erro.value.campo == "nota"


def test_comentario_vazio_ou_longo_demais_e_recusado(cliente, produto):
    with pytest.raises(AvaliacaoInvalida, match="Escreva"):
        _criar(cliente, produto, comentario="   ")
    with pytest.raises(AvaliacaoInvalida, match="1500"):
        _criar(cliente, produto, comentario="x" * 1501)


def test_quarta_foto_e_recusada_sem_gravar_nada(cliente, produto):
    """Avaliacao gravada sem as fotos que o cliente mandou seria publicada pela metade."""
    with pytest.raises(AvaliacaoInvalida, match="3 fotos"):
        _criar(cliente, produto, fotos=[_foto() for _ in range(4)])
    assert not Avaliacao.objects.exists()


def test_arquivo_que_nao_e_imagem_e_recusado(cliente, produto):
    """Extensao .png nao prova nada: um executavel renomeado tem que ser barrado."""
    with pytest.raises(AvaliacaoInvalida, match="nao e uma imagem"):
        _criar(cliente, produto, fotos=[_foto("virus.png", b"MZ\x90\x00" + b"0" * 20)])
    assert not Avaliacao.objects.exists()


def test_segunda_avaliacao_do_mesmo_cliente_e_conflito(cliente, produto):
    """A regra e do banco (indice unico): o if perderia para dois cliques ao mesmo tempo."""
    _criar(cliente, produto)
    with pytest.raises(AvaliacaoConflito) as erro:
        _criar(cliente, produto, nota=1)
    assert erro.value.codigo == "avaliacao_existente"
    assert Avaliacao.objects.count() == 1


def test_produto_que_nao_aceita_avaliacao_e_conflito(cliente, produto):
    produto.avaliacoes_permitidas = False
    produto.save()
    with pytest.raises(AvaliacaoConflito) as erro:
        _criar(cliente, produto)
    assert erro.value.codigo == "avaliacoes_fechadas"


def test_compra_verificada_so_com_pedido_pago_do_produto(cliente, produto):
    """Pedido cancelado nao comprova compra: o selo diria algo falso na vitrine."""
    cancelado = Pedido.objects.create(cliente=cliente, status=Pedido.Status.CANCELADO)
    ItemPedido.objects.create(pedido=cancelado, produto=produto, nome="Poltrona")
    assert _criar(cliente, produto).compra_verificada is False

    outro = Cliente.objects.create(email="bia@x.com", nome="Bia")
    pago = Pedido.objects.create(cliente=outro, status=Pedido.Status.CONCLUIDO)
    ItemPedido.objects.create(pedido=pago, produto=produto, nome="Poltrona")
    avaliacao = _criar(outro, produto)
    assert avaliacao.compra_verificada is True
    assert avaliacao.pedido == pago


def test_moderar_grava_quem_e_quando_e_limpa_motivo_ao_aprovar(cliente, produto, admin_logado):
    from apps.core.models import User

    usuario = User.objects.get(username="admin")
    avaliacao = _criar(cliente, produto)
    rejeitada = moderar(avaliacao.pk, Avaliacao.Status.REJEITADA, usuario, "Ofensivo")
    assert rejeitada.motivo_rejeicao == "Ofensivo"
    assert rejeitada.moderado_por == usuario and rejeitada.moderado_em

    aprovada = moderar(avaliacao.pk, Avaliacao.Status.APROVADA, usuario, "sobra")
    assert aprovada.status == Avaliacao.Status.APROVADA
    assert aprovada.motivo_rejeicao == ""


def test_rejeitada_libera_o_cliente_para_avaliar_de_novo(cliente, produto):
    """A rejeitada fica como historico, mas nao conta como "ja avaliou"."""
    primeira = _criar(cliente, produto)
    moderar(primeira.pk, Avaliacao.Status.REJEITADA, None, "Ofensivo")
    nova = _criar(cliente, produto, nota=4)
    assert nova.status == Avaliacao.Status.PENDENTE
    assert Avaliacao.objects.count() == 2
    with pytest.raises(AvaliacaoConflito) as erro:
        _criar(cliente, produto)
    assert erro.value.codigo == "avaliacao_existente"


def test_excluida_libera_o_cliente_para_avaliar_de_novo(cliente, produto):
    _criar(cliente, produto).delete()
    assert _criar(cliente, produto).status == Avaliacao.Status.PENDENTE


def test_reverter_rejeitada_com_outra_ativa_e_conflito(cliente, produto):
    """Desfazer a rejeicao deixaria duas ativas do mesmo cliente: o banco recusa."""
    primeira = _criar(cliente, produto)
    moderar(primeira.pk, Avaliacao.Status.REJEITADA, None, "Ofensivo")
    _criar(cliente, produto)
    with pytest.raises(AvaliacaoConflito) as erro:
        moderar(primeira.pk, Avaliacao.Status.APROVADA, None)
    assert erro.value.codigo == "avaliacao_existente"
    assert Avaliacao.objects.get(pk=primeira.pk).status == Avaliacao.Status.REJEITADA


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 32


def _video(nome="v.mp4", conteudo=MP4):
    return SimpleUploadedFile(nome, conteudo, content_type="video/mp4")


def test_video_entra_junto_das_fotos_mas_so_um(cliente, produto):
    avaliacao = _criar(cliente, produto, fotos=[_foto(), _video()])
    assert [f.imagem.name.rsplit(".", 1)[1] for f in avaliacao.fotos.all()] == ["png", "mp4"]

    outro = Cliente.objects.create(email="bia@x.com", nome="Bia")
    with pytest.raises(AvaliacaoInvalida) as erro:
        _criar(outro, produto, fotos=[_video(), _video("w.mp4")])
    assert erro.value.campo == "fotos"


def test_video_grande_demais_e_recusado(cliente, produto, monkeypatch):
    from apps.loja.services import midias_avaliacao

    monkeypatch.setattr(midias_avaliacao, "VIDEO_TAMANHO_MAXIMO", 10)
    with pytest.raises(AvaliacaoInvalida) as erro:
        _criar(cliente, produto, fotos=[_video()])
    assert erro.value.campo == "fotos"
    assert not Avaliacao.objects.exists()
