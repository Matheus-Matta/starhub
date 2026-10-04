# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woo_api', '0003_alter_chaveapi_metadados_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chaveapi',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalchaveapi',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
    ]
