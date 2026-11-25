"""Reserva da foto antes de mandar: dois envios juntos do mesmo produto nao a mandam em dobro.

O update roda sem trava (envio/base.py): dois workers viam a mesma foto sem vinculo e os
dois a mandavam. Antes da chamada, cada foto ganha o vinculo "pendente:<pk>"; quem segura o
segundo e o indice unico do banco (referencia_externa_unica), nao um `if`.

    with reservadas(enviador, obj, pendentes(enviador, obj)) as imagens:
        ...mutation com `imagens`, registrar(...)

Erro na chamada devolve a reserva. Worker que morreu no meio nao devolve: ela vence em
VALIDADE. Se a foto chegou a subir, a importacao a reconhece pelo nome do arquivo.
"""

from contextlib import contextmanager
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import ExternalReference, Origin
from apps.shopify import midias as vinculos

VALIDADE = timedelta(minutes=15)  # folga sobre o timeout de um envio de produto
RESERVA = {"reservada": True}


def vencida(vinculo):
    return vinculo.metadata == RESERVA and vinculo.updated_at < timezone.now() - VALIDADE


def _reservar(midia):
    chave = f"{vinculos.PENDENTE}{midia.pk}"
    try:
        with transaction.atomic():
            ExternalReference.all_objects.create(
                account_id=midia.account_id, platform=Origin.SHOPIFY,
                entity_type=vinculos.ENTIDADE, external_id=chave, object_id=str(midia.pk),
                metadata=RESERVA, origin=Origin.SHOPIFY)
        return True
    except IntegrityError:
        # A vencida passa para este envio; o filtro no UPDATE deixa so um assumir.
        return bool(vinculos.referencias(midia.account_id).filter(
            external_id=chave, metadata=RESERVA, updated_at__lt=timezone.now() - VALIDADE
        ).update(updated_at=timezone.now()))


def devolver(midias):
    for midia in midias:
        vinculos.referencias(midia.account_id).filter(
            external_id=f"{vinculos.PENDENTE}{midia.pk}", metadata=RESERVA).delete()


@contextmanager
def reservadas(grupos):
    meus = [(url, midias) for url, midias in grupos if _reservar(midias[0])]
    try:
        yield meus
    finally:
        # Registradas ja trocaram a reserva pelo id da loja; sobra a que falhou.
        devolver([midias[0] for _url, midias in meus])
