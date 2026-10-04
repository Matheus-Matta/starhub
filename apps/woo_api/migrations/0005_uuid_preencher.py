# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations

from apps.core.migracoes_uuid import preencher_uuid


class Migration(migrations.Migration):

    dependencies = [
        ('woo_api', '0004_uuid_adicionar'),
    ]

    operations = [
        migrations.RunPython(
            preencher_uuid('woo_api', 'ChaveApi'),
            migrations.RunPython.noop,
        ),
    ]
