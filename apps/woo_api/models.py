from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel
from apps.woo_api import chaves


class ChaveApi(BaseModel):
    class Permissao(models.TextChoices):
        LEITURA = "read", "Leitura"
        ESCRITA = "write", "Escrita"
        LEITURA_ESCRITA = "read_write", "Leitura e escrita"

    descricao = models.CharField("descricao", max_length=200)
    permissao = models.CharField(
        "permissao", max_length=10, choices=Permissao, default=Permissao.LEITURA_ESCRITA
    )
    chave_hash = models.CharField(max_length=64, unique=True, editable=False)
    segredo_hash = models.CharField(max_length=64, editable=False)
    final_chave = models.CharField("final da chave", max_length=7, editable=False)
    last_used_at = models.DateTimeField("ultimo acesso", null=True, blank=True, editable=False)
    expires_at = models.DateTimeField("expira em", null=True, blank=True)
    scopes = models.JSONField("escopos", default=list, blank=True)

    class Meta:
        verbose_name = "chave de API"
        verbose_name_plural = "chaves de API"
        ordering = ["-created_at"]
        permissions = [("usar_api", "Pode usar a API Woo com login JWT")]

    def __str__(self):
        return f"{self.descricao} (...{self.final_chave})"

    @property
    def expirada(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def gerar(self):
        chave, segredo = chaves.gerar_par()
        self.chave_hash = chaves.hash_de(chave)
        self.segredo_hash = chaves.hash_de(segredo)
        self.final_chave = chave[-7:]
        return chave, segredo

    def permite(self, metodo):
        if metodo in ("GET", "HEAD", "OPTIONS"):
            return self.permissao in (self.Permissao.LEITURA, self.Permissao.LEITURA_ESCRITA)
        return self.permissao in (self.Permissao.ESCRITA, self.Permissao.LEITURA_ESCRITA)
