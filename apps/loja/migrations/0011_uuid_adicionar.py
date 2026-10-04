# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loja', '0010_alter_categoria_metadados_alter_cliente_metadados_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoria',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalcategoria',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalcliente',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='clienteendereco',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalclienteendereco',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='cupom',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalcupom',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='entregapedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalentregapedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='itembundle',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalitembundle',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='itempedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalitempedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='midiaproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalmidiaproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='pagamentopedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalpagamentopedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='pedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalpedido',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='produto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='tag',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicaltag',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='tipovariante',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicaltipovariante',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='valordavarianteproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalvalordavarianteproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='valorvariante',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalvalorvariante',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='varianteproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
        migrations.AddField(
            model_name='historicalvarianteproduto',
            name='uuid',
            field=models.UUIDField(editable=False, null=True, verbose_name='uuid'),
        ),
    ]
