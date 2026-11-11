"""Base do ID do pedido sai da configuracao WooCommerce e vai para a FDC Sistemas.

Roda antes de integracoes.0032 apagar o campo: sem a copia, o ERP passaria a ver os
pedidos com o id do hub (1, 2...) e importaria por cima dos pedidos antigos dele.
"""

from django.db import migrations


def copiar_base(apps, schema_editor):
    integracao = apps.get_model("integracoes", "ConfiguracaoIntegracao")
    fdc = apps.get_model("woo_api", "ConfiguracaoFdc")
    bases = {}
    for conta, base in (integracao.objects.filter(plataforma="woocommerce")
                        .values_list("account_id", "base_id_pedido")):
        # Conta com duas lojas Woo: a maior base, para nenhum id voltar para tras.
        bases[conta] = max(bases.get(conta, 0), base or 0)
    for conta, base in bases.items():
        fdc.objects.update_or_create(account_id=conta, defaults={"base_id_pedido": base})


def devolver_base(apps, schema_editor):
    integracao = apps.get_model("integracoes", "ConfiguracaoIntegracao")
    fdc = apps.get_model("woo_api", "ConfiguracaoFdc")
    for conta, base in fdc.objects.values_list("account_id", "base_id_pedido"):
        integracao.objects.filter(account_id=conta, plataforma="woocommerce").update(
            base_id_pedido=base)


class Migration(migrations.Migration):

    dependencies = [
        ("integracoes", "0031_textos_servico_legado"),
        ("woo_api", "0008_configuracao_fdc"),
    ]

    operations = [migrations.RunPython(copiar_base, devolver_base)]
