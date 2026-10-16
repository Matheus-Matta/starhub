from django.db import models

from apps.core.models import BaseModel


class ContatoStarChats(BaseModel):
    configuracao = models.ForeignKey(
        "starchats.ConfiguracaoStarChats", on_delete=models.CASCADE, related_name="contatos"
    )
    cliente = models.ForeignKey(
        "loja.Cliente", on_delete=models.CASCADE, related_name="contatos_starchats"
    )
    contato_externo_id = models.CharField(max_length=100, blank=True)
    origem_externa_id = models.CharField(max_length=255, blank=True)
    conversa_externa_id = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "contato do StarChats"
        verbose_name_plural = "Contatos do StarChats"
        constraints = [
            models.UniqueConstraint(
                fields=["account", "configuracao", "cliente"],
                name="starchats_contato_unico",
            )
        ]

    def __str__(self):
        return str(self.cliente)


class EnvioStarChats(BaseModel):
    class Status(models.TextChoices):
        PENDENTE = "pending", "Pendente"
        PROCESSANDO = "running", "Processando"
        ENVIADO = "sent", "Enviado"
        FALHOU = "failed", "Falhou"

    conjunto = models.ForeignKey(
        "starchats.ConjuntoEnvio", on_delete=models.PROTECT, related_name="envios"
    )
    cliente = models.ForeignKey(
        "loja.Cliente", on_delete=models.PROTECT, related_name="envios_starchats"
    )
    tipo_objeto = models.CharField(max_length=20)
    objeto_id = models.CharField(max_length=100)
    evento = models.CharField(max_length=30)
    chave_deduplicacao = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDENTE)
    conteudo = models.TextField(blank=True)
    parametros = models.JSONField(default=dict, blank=True, editable=False)
    mensagem_externa_id = models.CharField(max_length=100, blank=True)
    erro = models.TextField(blank=True)
    processando_em = models.DateTimeField(null=True, blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "envio do StarChats"
        verbose_name_plural = "Historico de envios"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "chave_deduplicacao"],
                name="starchats_envio_nao_duplica",
            )
        ]

    def __str__(self):
        return f"{self.conjunto} - {self.get_status_display()}"
