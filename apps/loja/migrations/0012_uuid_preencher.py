# Gerada para o uuid do BaseModel (apps/core/migracoes_uuid.py explica o porque).

from django.db import migrations

from apps.core.migracoes_uuid import preencher_uuid


class Migration(migrations.Migration):

    dependencies = [
        ('loja', '0011_uuid_adicionar'),
    ]

    operations = [
        migrations.RunPython(
            preencher_uuid('loja', 'Categoria', 'Cliente', 'ClienteEndereco', 'Cupom', 'EntregaPedido', 'ItemBundle', 'ItemPedido', 'MidiaProduto', 'PagamentoPedido', 'Pedido', 'Produto', 'Tag', 'TipoVariante', 'ValorDaVarianteProduto', 'ValorVariante', 'VarianteProduto'),
            migrations.RunPython.noop,
        ),
    ]
