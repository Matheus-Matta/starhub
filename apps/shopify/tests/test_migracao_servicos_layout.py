"""A troca do vinculo unico para multisselecao preserva o servico escolhido."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ANTES = [("shopify", "0003_initial")]
DEPOIS = [("shopify", "0004_remove_apresentacaoservicoshopify_servico_alternativo_and_more")]


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(alvo)
    return executor.loader.project_state(alvo).apps


@pytest.mark.sem_conta
@pytest.mark.django_db(transaction=True)
def test_servico_alternativo_antigo_vira_item_da_multisselecao():
    apps = _migrar(ANTES)
    Account = apps.get_model("core", "Account")
    Servico = apps.get_model("loja", "Servico")
    Apresentacao = apps.get_model("shopify", "ApresentacaoServicoShopify")
    conta = Account.objects.create(name="Loja", slug="loja-layout")
    principal = Servico.objects.create(
        account=conta, nome="Montagem", nome_normalizado="montagem", sku="MONT")
    alternativo = Servico.objects.create(
        account=conta, nome="Garantia", nome_normalizado="garantia", sku="GAR")
    apresentacao = Apresentacao.objects.create(
        account=conta, servico=principal, tipo_campo="radio",
        servico_alternativo=alternativo)

    try:
        apps = _migrar(DEPOIS)
        Apresentacao = apps.get_model("shopify", "ApresentacaoServicoShopify")
        migrada = Apresentacao.objects.get(pk=apresentacao.pk)
        assert list(migrada.servicos_vinculados.values_list("pk", flat=True)) == [
            alternativo.pk]
    finally:
        _migrar(MigrationExecutor(connection).loader.graph.leaf_nodes())
