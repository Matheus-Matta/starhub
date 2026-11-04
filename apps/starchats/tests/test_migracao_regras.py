"""A mudanca de regra reutilizavel para regra filha preserva os cadastros."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ANTES = [("starchats", "0003_alter_configuracaostarchats_options_and_more")]
DEPOIS = [("starchats", "0004_remove_conjuntoenvio_regras_and_more")]


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(alvo)
    return executor.loader.project_state(alvo).apps


@pytest.mark.sem_conta
@pytest.mark.django_db(transaction=True)
def test_regra_reutilizada_e_copiada_para_cada_conjunto_sem_perder_dados():
    apps = _migrar(ANTES)
    Account = apps.get_model("core", "Account")
    Configuracao = apps.get_model("starchats", "ConfiguracaoStarChats")
    Modelo = apps.get_model("starchats", "ModeloMensagem")
    Conjunto = apps.get_model("starchats", "ConjuntoEnvio")
    Regra = apps.get_model("starchats", "RegraEnvio")
    conta = Account.objects.create(name="Loja", slug="loja")
    configuracao = Configuracao.objects.create(
        account=conta, url_base="https://chat.test", conta_externa_id=1
    )
    modelo = Modelo.objects.create(
        account=conta,
        configuracao=configuracao,
        caixa_entrada_id=1,
        nome="boas_vindas",
        idioma="pt_BR",
    )
    conjuntos = [
        Conjunto.objects.create(
            account=conta, nome=nome, evento="cliente.criado", modelo=modelo
        )
        for nome in ("Primeiro", "Segundo")
    ]
    regra = Regra.objects.create(
        account=conta,
        nome="Aceitou marketing",
        campo="cliente.aceita_marketing",
        operador="eq",
        valor="true",
    )
    for conjunto in conjuntos:
        conjunto.regras.add(regra)

    try:
        apps = _migrar(DEPOIS)
        Regra = apps.get_model("starchats", "RegraEnvio")
        regras = list(Regra.objects.filter(nome="Aceitou marketing").order_by("conjunto_id"))
        assert {item.conjunto_id for item in regras} == {item.pk for item in conjuntos}
        assert len(regras) == 2
        assert regras[0].uuid != regras[1].uuid
        assert all(item.valor == "true" for item in regras)
    finally:
        folhas = MigrationExecutor(connection).loader.graph.leaf_nodes()
        _migrar(folhas)
