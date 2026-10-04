# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loja', '0012_uuid_preencher'),
    ]

    operations = [
        migrations.AlterField(
            model_name='categoria',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalcategoria',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='cliente',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalcliente',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='clienteendereco',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalclienteendereco',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='cupom',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalcupom',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='entregapedido',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalentregapedido',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='itembundle',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalitembundle',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='itempedido',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalitempedido',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='midiaproduto',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalmidiaproduto',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='pagamentopedido',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalpagamentopedido',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='pedido',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalpedido',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='produto',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalproduto',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='tag',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicaltag',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='tipovariante',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicaltipovariante',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='valordavarianteproduto',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalvalordavarianteproduto',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='valorvariante',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalvalorvariante',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='varianteproduto',
            name='uuid',
            field=models.UUIDField(unique=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='historicalvarianteproduto',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='uuid'),
        ),
    ]
