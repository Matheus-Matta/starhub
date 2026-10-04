"""Move o id do line_item do Shopify dos metadados do ItemPedido para o vinculo.

Os metadados do item saem no `meta_data` do line_item da API Woo: o id do Shopify
ali misturava dado do marketplace no registro do hub. Sem mover, o proximo
orders/updated nao acharia os itens ja importados e criaria todos de novo.
"""

from django.db import migrations

CHAVE = "_shopify_line_item_id"
ENTIDADE = "itens_pedido"


def _gid(valor):
    texto = str(valor or "")
    if not texto or texto.startswith("gid://"):
        return texto
    return f"gid://shopify/LineItem/{texto}"


def mover_para_o_vinculo(apps, schema_editor):
    ItemPedido = apps.get_model("loja", "ItemPedido")
    ExternalReference = apps.get_model("core", "ExternalReference")
    for item in ItemPedido._base_manager.exclude(metadados=[]).iterator():
        lista = item.metadados if isinstance(item.metadados, list) else []
        valor = next((m.get("value") for m in lista if m.get("key") == CHAVE), None)
        if valor is None:
            continue
        if _gid(valor):
            ExternalReference._base_manager.get_or_create(
                account_id=item.account_id, platform="shopify", entity_type=ENTIDADE,
                external_id=_gid(valor),
                defaults={"object_id": str(item.pk), "origin": "shopify", "metadata": {}},
            )
        item.metadados = [m for m in lista if m.get("key") != CHAVE]
        item.save(update_fields=["metadados"])


def voltar_para_o_item(apps, schema_editor):
    ItemPedido = apps.get_model("loja", "ItemPedido")
    ExternalReference = apps.get_model("core", "ExternalReference")
    vinculos = ExternalReference._base_manager.filter(platform="shopify", entity_type=ENTIDADE)
    for vinculo in vinculos.iterator():
        item = ItemPedido._base_manager.filter(pk=vinculo.object_id).first()
        if item is None:
            continue
        lista = [m for m in (item.metadados or []) if m.get("key") != CHAVE]
        proximo = max((m.get("id", 0) for m in lista), default=0) + 1
        numero = vinculo.external_id.rsplit("/", 1)[-1]
        item.metadados = [*lista, {"id": proximo, "key": CHAVE, "value": numero}]
        item.save(update_fields=["metadados"])
    vinculos.delete()


class Migration(migrations.Migration):
    dependencies = [("shopify", "0001_midias_no_vinculo")]

    operations = [migrations.RunPython(mover_para_o_vinculo, voltar_para_o_item)]
