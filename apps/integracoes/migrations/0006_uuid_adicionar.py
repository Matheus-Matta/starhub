# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integracoes', '0005_execucaointegracao_falhas_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracaointegracao',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalconfiguracaointegracao',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='execucaointegracao',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalexecucaointegracao',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
    ]
