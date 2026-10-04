# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_alter_accessprofile_metadados_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='accessprofile',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalaccessprofile',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='address',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicaladdress',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='externalreference',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalexternalreference',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='publicationpolicy',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalpublicationpolicy',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='publicationstate',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalpublicationstate',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='saleschannel',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalsaleschannel',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
    ]
