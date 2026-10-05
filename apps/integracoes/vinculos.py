"""Vinculo id do marketplace <-> registro do hub (ExternalReference), por plataforma.

    vinculos = Vinculos("suri")
    vinculos.referenciar("produtos", "48349", produto)
    vinculos.existente("produtos", Produto, "48349")   # -> produto

O id externo e por recurso (produto 15 e pedido 15 sao coisas diferentes): o
entity_type separa. Variacao vai em "variantes", com o id do pai em external_parent_id.
"""

from django.db import IntegrityError, transaction

from apps.core.models import ExternalReference


class Vinculos:
    def __init__(self, plataforma):
        self.plataforma = plataforma

    def _filtro(self, recurso, externo_id):
        return {"platform": self.plataforma, "entity_type": recurso,
                "external_id": str(externo_id)}

    def objeto_id(self, recurso, externo_id):
        return ExternalReference.objects.filter(**self._filtro(recurso, externo_id)).values_list(
            "object_id", flat=True).first()

    def existente(self, recurso, modelo, externo_id):
        pk = self.objeto_id(recurso, externo_id) if externo_id not in (None, "") else None
        return modelo.objects.filter(pk=pk).first() if pk else None

    def referenciar(self, recurso, externo_id, obj, pai="", metadata=None):
        """Grava o vinculo; dois webhooks juntos batem no indice unico e o segundo so le."""
        if externo_id in (None, ""):
            return obj
        defaults = {"object_id": str(obj.pk), "origin": self.plataforma,
                    "external_parent_id": str(pai)}
        if metadata is not None:
            defaults["metadata"] = metadata
        try:
            with transaction.atomic():
                ExternalReference.objects.update_or_create(**self._filtro(recurso, externo_id),
                                                           defaults=defaults)
        except IntegrityError:  # a outra gravacao venceu; o vinculo dela vale
            pass
        return obj

    def externo_id(self, recurso, obj_pk):
        """Id no marketplace do registro do hub, ou None se ainda nao foi para la."""
        return ExternalReference.objects.filter(
            platform=self.plataforma, entity_type=recurso, object_id=str(obj_pk)).values_list(
            "external_id", flat=True).first()

    def referencia(self, recurso, obj_pk):
        return ExternalReference.objects.filter(
            platform=self.plataforma, entity_type=recurso, object_id=str(obj_pk)).first()
