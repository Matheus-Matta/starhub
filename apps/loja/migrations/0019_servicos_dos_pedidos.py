from django.db import migrations


def cadastrar(apps, schema_editor):
    # Pedidos importados antes do cadastro de servicos: cada servico deles ganha
    # cadastro (id e SKU para a API Woo). Os pedidos nao sao alterados.
    from apps.loja.services.servicos import cadastrar_dos_pedidos

    cadastrar_dos_pedidos(apps.get_model("loja", "Pedido"), apps.get_model("loja", "Servico"))


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0018_servicos"),
    ]

    # Desfazer apaga a tabela (0018); aqui nao ha o que voltar.
    operations = [migrations.RunPython(cadastrar, migrations.RunPython.noop)]
