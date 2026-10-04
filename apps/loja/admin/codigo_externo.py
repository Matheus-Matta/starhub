"""Coluna "Codigo externo" das listas: o id do vinculo do marketplace de origem.

O ExternalReference liga por `object_id` em texto (nao ha FK), entao nao da para
prefetch. Uma subconsulta na propria listagem traz o codigo junto das linhas: o
numero de consultas nao depende de quantas linhas a pagina tem.
"""

from django.contrib import admin
from django.db.models import CharField, OuterRef, Subquery
from django.db.models.functions import Cast
from django.utils.html import format_html

from apps.core.models import ExternalReference

SEM_CODIGO = "-"


def formatar_codigo(externo_id):
    """gid://shopify/Product/123 vira 123; id vazio (criado no hub) vira traco."""
    if not externo_id:
        return SEM_CODIGO
    return str(externo_id).rstrip("/").rsplit("/", 1)[-1] or SEM_CODIGO


class CodigoExternoMixin:
    """Poe a coluna `codigo_externo` no ModelAdmin; `entidade_externa` e o entity_type."""

    entidade_externa = ""

    def get_queryset(self, request):
        vinculo = ExternalReference.objects.filter(
            platform=OuterRef("origin"),
            entity_type=self.entidade_externa,
            object_id=Cast(OuterRef("pk"), CharField()),
        ).order_by("pk").values("external_id")[:1]
        # account tambem: a lista lia uma vez por linha (N+1).
        return (super().get_queryset(request).select_related("account")
                .annotate(_codigo_externo=Subquery(vinculo)))

    @admin.display(description="codigo externo", ordering="_codigo_externo")
    def codigo_externo(self, obj):
        return format_html('<span class="nowrap">{}</span>',
                           formatar_codigo(getattr(obj, "_codigo_externo", None)))
