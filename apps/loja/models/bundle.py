from django.core.exceptions import ValidationError
from django.db import models

from apps.core.tenant.validators import validate_same_account

from .base import ComDatas


class ItemBundle(ComDatas):
    bundle_product = models.ForeignKey(
        "loja.Produto", verbose_name="produto bundle", on_delete=models.CASCADE,
        related_name="componentes"
    )
    component_variant = models.ForeignKey(
        "loja.VarianteProduto", verbose_name="componente", on_delete=models.PROTECT,
        related_name="bundles",
    )
    quantity = models.PositiveIntegerField("quantidade", default=1)

    class Meta:
        verbose_name = "componente do bundle"
        verbose_name_plural = "componentes do bundle"
        constraints = [models.UniqueConstraint(
            fields=["bundle_product", "component_variant"], name="bundle_componente_unico"
        )]

    def clean(self):
        validate_same_account(self, self.bundle_product, self.component_variant)
        if self.bundle_product.tipo != self.bundle_product.Tipo.BUNDLE:
            raise ValidationError("Componentes so podem ser ligados a produto bundle.")
