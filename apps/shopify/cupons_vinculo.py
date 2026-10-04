"""Dados do desconto que so o Shopify conhece, guardados no vinculo do cupom.

O Cupom do hub nao leva nada de marketplace: tipo, status real, codigos, frete
maximo e gids que o hub nao entende ficam no `metadata` da ExternalReference
(platform shopify, entity "cupons"), independente de qualquer outro marketplace.
"""

from apps.core.models import ExternalReference, Origin

ENTIDADE = "cupons"


def vinculo(cupom):
    return ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=ENTIDADE, object_id=str(cupom.pk)).first()


def dados(cupom):
    referencia = vinculo(cupom)
    return (referencia.metadata or {}) if referencia else {}


def gravar(referencia, novos, substituir=False):
    """Grava `novos` no vinculo. `substituir` descarta o que havia (importacao
    completa refaz tudo); sem ele mescla (corpo magro de webhook e o envio)."""
    if referencia is None:
        return
    base = {} if substituir else (referencia.metadata or {})
    referencia.metadata = {**base, **novos}
    referencia.save(update_fields=["metadata", "updated_at"])
