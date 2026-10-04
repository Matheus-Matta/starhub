# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations

from apps.core.migracoes_uuid import preencher_uuid


class Migration(migrations.Migration):

    dependencies = [
        ('integracoes', '0006_uuid_adicionar'),
    ]

    operations = [
        migrations.RunPython(
            preencher_uuid('integracoes', 'ConfiguracaoIntegracao', 'ExecucaoIntegracao'),
            migrations.RunPython.noop,
        ),
    ]
