from django.db import models

from apps.core.models import BaseModel


class ModeloMensagem(BaseModel):
    configuracao = models.ForeignKey(
        "starchats.ConfiguracaoStarChats",
        on_delete=models.CASCADE,
        related_name="modelos",
    )
    caixa_entrada_id = models.PositiveBigIntegerField("ID da caixa")
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
                fields=["account", "configuracao", "caixa_entrada_id", "nome", "idioma"],
                name="starchats_modelo_unico_por_caixa",
            )
        ]

    def __str__(self):
        return f"{self.nome} ({self.idioma})"
