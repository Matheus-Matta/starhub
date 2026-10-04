"""Todo registro ganha um uuid unico, inclusive os que ja existiam antes da migration.

Com AddField(default=uuid4) o Django calcula o default UMA vez e grava o mesmo valor
em todas as linhas antigas: o indice unico nao nasce e a migration quebra em banco
com dados. A migration preenche linha a linha antes de ligar o unique.
"""

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.models import ExternalReference

ANTES = [("core", "0005_uuid_adicionar")]


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(alvo)
    return executor.loader.project_state(alvo).apps


def _ultimas():
    return MigrationExecutor(connection).loader.graph.leaf_nodes()


@pytest.mark.sem_conta
@pytest.mark.django_db(transaction=True)
def test_registros_antigos_ganham_uuids_diferentes_e_o_historico_acompanha():
    apps = _migrar(ANTES)
    Account = apps.get_model("core", "Account")
    Referencia = apps.get_model("core", "ExternalReference")
    Historico = apps.get_model("core", "HistoricalExternalReference")
    conta = Account.objects.create(name="A", slug="a")
    ids = [Referencia.objects.create(account=conta, platform="shopify", entity_type="produtos",
                                     object_id=str(n), external_id=f"gid://{n}").pk
           for n in (1, 2)]
    Historico.objects.create(id=ids[0], account_id=conta.pk, platform="shopify",
                             entity_type="produtos", object_id="1", external_id="gid://1",
                             history_date=timezone.now(), history_type="+",
                             created_at=timezone.now(), updated_at=timezone.now())
    try:
        apps = _migrar(_ultimas())
        Referencia = apps.get_model("core", "ExternalReference")
        Historico = apps.get_model("core", "HistoricalExternalReference")
        uuids = dict(Referencia.objects.values_list("pk", "uuid"))
        assert None not in uuids.values()
        assert uuids[ids[0]] != uuids[ids[1]]
        assert Historico.objects.get(id=ids[0]).uuid == uuids[ids[0]]
    finally:
        _migrar(_ultimas())


@pytest.mark.django_db
def test_registro_novo_ganha_uuid_sozinho_e_o_banco_recusa_repetido(conta):
    """A defesa contra uuid repetido e o indice unico do banco, nao o default."""
    um = ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                          object_id="1", external_id="gid://1")
    dois = ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                            object_id="2", external_id="gid://2")

    assert isinstance(um.uuid, uuid.UUID) and um.uuid != dois.uuid
    assert um.historical.first().uuid == um.uuid
    with pytest.raises(IntegrityError), transaction.atomic():
        ExternalReference.objects.filter(pk=dois.pk).update(uuid=um.uuid)
