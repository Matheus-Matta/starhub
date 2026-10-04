"""Pedido de marketplace com o numero da loja em `number` passa a ter numero do hub.

Regra nova: `number` e sempre do hub (novo_numero_pedido); o numero do marketplace
fica em `external_number`. O importador antigo gravava "1001" (ou "SHOPIFY-<id>")
em `number`; aqui o numero vai para `external_number` quando ele esta vazio e o
pedido ganha um numero do hub. Pedido do hub, do ERP (api) e de importacao de
planilha ja nasceram com o numero do hub e ficam como estao.

Reverse e noop: o numero antigo continua em external_number, e voltar exigiria
saber qual numero foi trocado.
"""

import re
import secrets

from django.db import migrations

NAO_MARKETPLACE = ("starhub", "api", "import")
NUMERO_DO_HUB = re.compile(r"^SH-[0-9A-F]{10}$")


def _sorteio():
    # Copia de novo_numero_pedido (apps/loja/models/pedido.py): a migracao nao pode
    # depender de funcao que muda depois.
    return secrets.token_hex(5).upper()


def _numero_livre(Pedido, conta_id):
    while True:
        numero = f"SH-{_sorteio()}"
        if not Pedido._base_manager.filter(account_id=conta_id, number=numero).exists():
            return numero


def numero_do_hub(apps, schema_editor):
    Pedido = apps.get_model("loja", "Pedido")
    pedidos = Pedido._base_manager.exclude(origin__in=NAO_MARKETPLACE).order_by("pk")
    for pk, conta_id, numero, externo in pedidos.values_list(
        "pk", "account_id", "number", "external_number"
    ):
        if NUMERO_DO_HUB.match(numero or ""):
            continue
        # update(): Pedido.save nao tem regra sobre o numero, e o historico/auditoria
        # nao precisa de uma linha por pedido para uma troca de formato.
        Pedido._base_manager.filter(pk=pk).update(
            number=_numero_livre(Pedido, conta_id),
            external_number=externo or numero,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0013_uuid_unico"),
    ]

    operations = [
        migrations.RunPython(numero_do_hub, migrations.RunPython.noop),
    ]
