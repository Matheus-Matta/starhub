# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integracoes', '0007_uuid_preencher'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configuracaointegracao',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalconfiguracaointegracao',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='execucaointegracao',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalexecucaointegracao',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
    ]
