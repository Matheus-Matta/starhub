from django.contrib.auth.models import Group
from django.db import models

from .base import BaseModel


class AccessProfile(BaseModel):
    name = models.CharField("nome", max_length=100)
    code = models.SlugField("codigo", max_length=50)
    group = models.ForeignKey(
        Group, verbose_name="grupo interno", on_delete=models.PROTECT,
        related_name="access_profiles",
    )
    is_system = models.BooleanField("perfil do sistema", default=False)

    class Meta:
        verbose_name = "perfil de acesso"
        verbose_name_plural = "perfis de acesso"
        constraints = [
            models.UniqueConstraint(fields=["account", "code"], name="perfil_codigo_conta_unico"),
        ]

    def __str__(self):
        return self.name
