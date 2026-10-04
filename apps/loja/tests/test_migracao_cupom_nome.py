"""A migration do nome unico renomeia os repetidos antes de criar o indice."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ANTES = [("loja", "0007_alter_historicalproduto_descricao_and_more")]
DEPOIS = [("loja", "0008_cupom_nome_unico")]


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(alvo)
    return executor.loader.project_state(alvo).apps


@pytest.mark.sem_conta
@pytest.mark.django_db(transaction=True)
def test_nomes_repetidos_na_conta_ganham_sufixo_por_ordem_de_id():
    """Sem desduplicar, o indice unico falha na criacao e a migration nao aplica."""
    apps = _migrar(ANTES)
    Account = apps.get_model("core", "Account")
    Cupom = apps.get_model("loja", "Cupom")
    conta = Account.objects.create(name="A", slug="a")
    outra = Account.objects.create(name="B", slug="b")

    def cupom(conta_, nome, codigo):
        return Cupom.objects.create(account=conta_, name=nome, code=codigo,
                                    discount_type="percentage", value=10).pk

    ids = [cupom(conta, "Promo", "A1"), cupom(conta, "Promo", "A2"),
           cupom(conta, "Promo (2)", "A3"), cupom(conta, "Promo", "A4"),
           cupom(outra, "Promo", "B1")]
    try:
        apps = _migrar(DEPOIS)
        Cupom = apps.get_model("loja", "Cupom")
        nomes = dict(Cupom.objects.values_list("pk", "name"))
        assert [nomes[pk] for pk in ids] == [
            "Promo", "Promo (3)", "Promo (2)", "Promo (4)", "Promo"]
    finally:
        _migrar(MigrationExecutor(connection).loader.graph.leaf_nodes())
