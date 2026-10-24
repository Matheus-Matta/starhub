from django.db import migrations


def separar(apps, schema_editor):
    from apps.loja.services.servicos_regras import separar_regras_por_tipo

    separar_regras_por_tipo(apps.get_model("loja", "RegraServico"))


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0022_regra_servico_tipo"),
    ]

    # Desfazer apaga o campo tipo (0022); as regras separadas continuam valendo juntas.
    operations = [migrations.RunPython(separar, migrations.RunPython.noop)]
