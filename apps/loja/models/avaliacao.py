from django.conf import settings
from django.db import models
from django.db.models import Q

from .base import ComDatas

FOTOS_MAXIMO = 3


class Avaliacao(ComDatas):
    """Avaliacao de produto enviada pelo cliente; so a APROVADA vai para a loja."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        APROVADA = "aprovada", "Aprovada"
        REJEITADA = "rejeitada", "Rejeitada"

    produto = models.ForeignKey(
        "loja.Produto", verbose_name="produto", on_delete=models.PROTECT, related_name="avaliacoes"
    )
    cliente = models.ForeignKey(
        "loja.Cliente", verbose_name="cliente", on_delete=models.PROTECT, related_name="avaliacoes"
    )
    # Foto do nome na hora do envio: se o cliente mudar o cadastro, o publicado nao muda.
    nome_publico = models.CharField("nome publico", max_length=80)
    nota = models.PositiveSmallIntegerField("nota")
    comentario = models.TextField("comentario", max_length=1500)
    status = models.CharField(
        "status", max_length=20, choices=Status, default=Status.PENDENTE, db_index=True
    )
    motivo_rejeicao = models.CharField("motivo da rejeicao", max_length=255, blank=True)
    moderado_em = models.DateTimeField("moderado em", null=True, blank=True)
    moderado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="moderado por", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    compra_verificada = models.BooleanField("compra verificada", default=False)
    pedido = models.ForeignKey(
        "loja.Pedido", verbose_name="pedido", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    publicada_em = models.DateTimeField("publicada na loja em", null=True, blank=True)

    class Meta:
        verbose_name = "avaliacao"
        verbose_name_plural = "avaliacoes"
        ordering = ["-created_at"]
        constraints = [
            # "1 cliente = 1 avaliacao por produto" fica no banco: um if perderia a corrida
            # de dois envios ao mesmo tempo (duplo clique no tema). A rejeitada fica de
            # historico e nao conta: o cliente pode avaliar de novo.
            models.UniqueConstraint(
                fields=["account", "produto", "cliente"],
                condition=~Q(status="rejeitada"),
                name="avaliacao_unica_por_cliente",
            ),
            models.CheckConstraint(
                condition=Q(nota__gte=1, nota__lte=5), name="avaliacao_nota_1_a_5"
            ),
        ]

    def __str__(self):
        return f"{self.nome_publico} - {self.nota}/5"


class FotoAvaliacao(ComDatas):
    avaliacao = models.ForeignKey(
        Avaliacao, verbose_name="avaliacao", on_delete=models.CASCADE, related_name="fotos"
    )
    imagem = models.FileField("imagem", upload_to="avaliacoes/%Y/%m/")
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "foto da avaliacao"
        verbose_name_plural = "fotos da avaliacao"
        ordering = ["ordem"]
        constraints = [models.UniqueConstraint(
            fields=["avaliacao", "ordem"], name="foto_avaliacao_ordem_unica"
        )]

    def __str__(self):
        return f"{'Video' if self.e_video else 'Foto'} {self.ordem + 1}"

    @property
    def e_video(self):
        # A extensao vem da assinatura conferida no envio (midias_avaliacao.validar).
        return self.imagem.name.lower().endswith((".mp4", ".mov", ".webm"))
