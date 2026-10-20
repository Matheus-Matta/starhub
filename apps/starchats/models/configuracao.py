from django.db import models

from apps.core.models import BaseModel
from apps.integracoes import segredos


class ConfiguracaoStarChats(BaseModel):
    url_base = models.URLField(
        "URL do StarChats",
        help_text="Endereco da instalacao, por exemplo https://chat.suaempresa.com.br.",
    )
    conta_externa_id = models.PositiveBigIntegerField(
        "ID da conta no StarChats",
        help_text="Numero da conta exibido no painel do StarChats.",
    )
    token_criptografado = models.TextField(editable=False, blank=True)
    caixa_entrada_id = models.PositiveBigIntegerField(
        "caixa do WhatsApp oficial", null=True, blank=True
    )
    caixa_entrada_nome = models.CharField(max_length=150, blank=True, editable=False)
    caixas_disponiveis = models.JSONField(default=list, blank=True, editable=False)
    sincronizado_em = models.DateTimeField(null=True, blank=True, editable=False)
    ultimo_erro = models.TextField(blank=True, editable=False)

    class Meta:
        verbose_name = "configuracao do StarChats"
        verbose_name_plural = "StarChats"
        constraints = [
            models.UniqueConstraint(
                fields=["account"], name="starchats_configuracao_unica_por_conta"
            )
        ]

    def __str__(self):
        return "StarChats"

    def save(self, *args, **kwargs):
        self.url_base = (self.url_base or "").rstrip("/")
        super().save(*args, **kwargs)

    @property
    def token_acesso(self):
        return segredos.descriptografar(self.token_criptografado)

    @token_acesso.setter
    def token_acesso(self, valor):
        self.token_criptografado = segredos.criptografar(valor)
