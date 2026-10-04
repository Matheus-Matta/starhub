# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woo_api', '0005_uuid_preencher'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chaveapi',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalchaveapi',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
    ]
