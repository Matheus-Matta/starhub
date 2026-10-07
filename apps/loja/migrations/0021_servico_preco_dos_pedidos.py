from django.db import migrations


def preencher(apps, schema_editor):
    # Servico criado sozinho pelo pedido nasceu sem preco: recebe o ultimo preco pago
    # por ele. So muda Servico com preco zero; pedidos nao sao alterados.
    from apps.loja.services.servicos import preencher_precos_dos_pedidos

    preencher_precos_dos_pedidos(apps.get_model("loja", "Pedido"),
                                 apps.get_model("loja", "Servico"))


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0020_servico_preco_e_regras"),
    ]

    # Desfazer apaga o campo preco (0020); aqui nao ha o que voltar.
    operations = [migrations.RunPython(preencher, migrations.RunPython.noop)]
