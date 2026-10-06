"""Contas que ja existiam ganham o SMTP e a configuracao de notificacao (tudo desligado).

Conta nova recebe as duas no post_save (apps/notificacoes/contas.py).
"""

import uuid

from django.db import migrations


def criar(apps, schema_editor):
    Account = apps.get_model("core", "Account")
    for nome in ("ConfiguracaoEmail", "ConfiguracaoNotificacao"):
        modelo = apps.get_model("notificacoes", nome)
        tem = set(modelo.objects.values_list("account_id", flat=True))
        modelo.objects.bulk_create([modelo(account_id=conta, uuid=uuid.uuid4())
                                    for conta in Account.objects.values_list("pk", flat=True)
                                    if conta not in tem])


class Migration(migrations.Migration):
    dependencies = [("notificacoes", "0001_initial"), ("core", "0008_plataformas_woocommerce_suri")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
