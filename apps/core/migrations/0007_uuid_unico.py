# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_uuid_preencher'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accessprofile',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalaccessprofile',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='address',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicaladdress',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='externalreference',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalexternalreference',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='publicationpolicy',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalpublicationpolicy',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='publicationstate',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalpublicationstate',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='saleschannel',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalsaleschannel',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
    ]
