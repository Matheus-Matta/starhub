"""Criacao e moderacao de avaliacoes de produto.

Quem chama (a API do tema, o admin) so traduz a entrada; as regras ficam aqui:
nota de 1 a 5, comentario ate 1500 caracteres, ate 3 fotos (uma delas pode ser video),
produto que aceita
avaliacao e uma avaliacao por cliente e produto (indice unico no banco).
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import Origin
from apps.loja.models import Avaliacao, FotoAvaliacao, Pedido
from apps.loja.models.avaliacao import FOTOS_MAXIMO
from apps.loja.services import midias_avaliacao

COMENTARIO_MAXIMO = 1500


class AvaliacaoInvalida(Exception):
    """Entrada errada (nota, texto, foto): o cliente corrige e envia de novo."""

    def __init__(self, campo, mensagem):
        super().__init__(mensagem)
        self.campo = campo


class AvaliacaoConflito(Exception):
    """O estado nao deixa avaliar (ja avaliou, produto fechado): reenviar nao resolve."""

    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        self.codigo = codigo


def nome_publico(cliente):
    """"Matheus Silva" vira "Matheus S.": o sobrenome inteiro nao vai para a vitrine."""
    nome = (cliente.nome or "").strip().split(" ")[0]
    sobrenome = (cliente.sobrenome or "").strip()
    if not nome:
        return "Cliente"
    return f"{nome} {sobrenome[0].upper()}." if sobrenome else nome


def pedido_que_comprova(cliente, produto):
    """Pedido pago do cliente com o produto; None se ele nao comprou."""
    return (Pedido.objects.filter(cliente=cliente, status__in=Pedido.PAGOS,
                                  itens__produto=produto)
            .order_by("-paid_at", "-pk").first())


def _nota(valor):
    try:
        nota = int(str(valor).strip())
    except (TypeError, ValueError):
        nota = 0
    if not 1 <= nota <= 5:
        raise AvaliacaoInvalida("nota", "Escolha uma nota de 1 a 5 estrelas.")
    return nota


def _comentario(valor):
    texto = str(valor or "").strip()
    if not texto:
        raise AvaliacaoInvalida("comentario", "Escreva um comentario sobre o produto.")
    if len(texto) > COMENTARIO_MAXIMO:
        raise AvaliacaoInvalida(
            "comentario", f"O comentario passa de {COMENTARIO_MAXIMO} caracteres; encurte o texto."
        )
    return texto


def _fotos(arquivos):
    arquivos = list(arquivos or [])
    if len(arquivos) > FOTOS_MAXIMO:
        raise AvaliacaoInvalida("fotos", f"Envie no maximo {FOTOS_MAXIMO} fotos ou videos.")
    extensoes = []
    for arquivo in arquivos:
        try:
            extensoes.append(midias_avaliacao.validar(arquivo))
        except ValidationError as erro:
            raise AvaliacaoInvalida("fotos", erro.messages[0]) from erro
    videos = sum(midias_avaliacao.e_video(extensao) for extensao in extensoes)
    if videos > midias_avaliacao.VIDEOS_MAXIMO:
        raise AvaliacaoInvalida("fotos", f"Envie no maximo {midias_avaliacao.VIDEOS_MAXIMO} video.")
    return list(zip(arquivos, extensoes, strict=True))


def criar_avaliacao(*, cliente, produto, nota, comentario, fotos=(), origin=Origin.STARHUB):
    """Grava a avaliacao PENDENTE com as fotos; levanta AvaliacaoInvalida/Conflito."""
    # Tudo validado antes de gravar: foto recusada nao deixa avaliacao pela metade.
    nota = _nota(nota)
    comentario = _comentario(comentario)
    fotos = _fotos(fotos)
    if not produto.avaliacoes_permitidas:
        raise AvaliacaoConflito("avaliacoes_fechadas", "Este produto nao aceita avaliacoes.")
    pedido = pedido_que_comprova(cliente, produto)
    with transaction.atomic():
        try:
            with transaction.atomic():
                avaliacao = Avaliacao.objects.create(
                    produto=produto, cliente=cliente, nome_publico=nome_publico(cliente),
                    nota=nota, comentario=comentario,
                    compra_verificada=pedido is not None, pedido=pedido, origin=origin,
                )
        except IntegrityError as erro:
            raise AvaliacaoConflito(
                "avaliacao_existente", "Voce ja avaliou este produto."
            ) from erro
        for ordem, (arquivo, extensao) in enumerate(fotos):
            foto = FotoAvaliacao(avaliacao=avaliacao, ordem=ordem)
            foto.imagem.save(f"{uuid.uuid4().hex}{extensao}", arquivo, save=False)
            foto.save()
    return avaliacao


def moderar(avaliacao_id, status, usuario, motivo=""):
    """Aprova ou rejeita. save() (e nao update()) para o envio a loja ser disparado."""
    with transaction.atomic():
        # Relida depois do lock: dois moderadores ao mesmo tempo, vale o ultimo inteiro.
        avaliacao = Avaliacao.objects.select_for_update().get(pk=avaliacao_id)
        avaliacao.status = status
        avaliacao.motivo_rejeicao = motivo if status == Avaliacao.Status.REJEITADA else ""
        avaliacao.moderado_em = timezone.now()
        avaliacao.moderado_por = usuario if getattr(usuario, "pk", None) else None
        try:
            with transaction.atomic():
                avaliacao.save()
        except IntegrityError as erro:
            # Desfazer uma rejeicao quando o cliente ja mandou outra: ficariam duas ativas.
            raise AvaliacaoConflito(
                "avaliacao_existente",
                "O cliente ja tem outra avaliacao deste produto; exclua uma delas antes.",
            ) from erro
    return avaliacao
