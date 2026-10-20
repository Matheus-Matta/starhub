from django.db import models

from apps.core.models import BaseModel


class ModeloMensagem(BaseModel):
    plataforma = models.CharField(
        "plataforma de mensagens",
        max_length=50,
        default="starchats",
        db_index=True,
        help_text="Provedor que sincronizou e envia este modelo.",
    )
    configuracao = models.ForeignKey(
        "starchats.ConfiguracaoStarChats",
        on_delete=models.CASCADE,
        related_name="modelos",
        null=True,
        blank=True,
        verbose_name="configuracao do StarChats",
    )
    caixa_entrada_id = models.PositiveBigIntegerField("ID do canal")
    identificador_externo = models.CharField(max_length=150, blank=True)
    nome = models.CharField(max_length=255)
    idioma = models.CharField(max_length=20)
    categoria = models.CharField(max_length=30, blank=True)
    situacao = models.CharField(max_length=30, blank=True)
    conteudo = models.TextField("texto do modelo", blank=True)
    componentes = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        verbose_name = "modelo de mensagem"
        verbose_name_plural = "Modelos de mensagem"
        ordering = ["nome", "idioma"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "account",
                    "plataforma",
                    "caixa_entrada_id",
                    "nome",
                    "idioma",
                ],
                name="starchats_modelo_unico_por_caixa",
            )
        ]

    def __str__(self):
        return f"{self.nome} ({self.idioma})"
