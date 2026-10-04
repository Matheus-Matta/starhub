# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations

from apps.core.migracoes_uuid import preencher_uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_uuid_adicionar'),
    ]

    operations = [
        migrations.RunPython(
            preencher_uuid('core', 'AccessProfile', 'Address', 'ExternalReference', 'PublicationPolicy', 'PublicationState', 'SalesChannel'),
            migrations.RunPython.noop,
        ),
    ]
