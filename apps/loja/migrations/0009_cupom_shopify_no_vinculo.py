"""Tira metadata["shopify"] do Cupom e leva para o vinculo (ExternalReference) do Shopify.

O cupom do hub nao guarda dado de marketplace. Cupom sem vinculo que ainda traga o
gid do desconto ganha o vinculo; sem gid nao ha onde guardar e a chave fica como esta.
"""

from django.db import migrations


def _vinculos(apps):
    return apps.get_model("core", "ExternalReference")._base_manager


def para_o_vinculo(apps, schema_editor):
    Cupom = apps.get_model("loja", "Cupom")
    vinculos = _vinculos(apps)
    for cupom in Cupom._base_manager.all():
        shopify = (cupom.metadata or {}).get("shopify")
        if not isinstance(shopify, dict):
            continue
        ref = vinculos.filter(platform="shopify", entity_type="cupons",
                              object_id=str(cupom.pk)).first()
        if ref is None and shopify.get("id"):
            ref, _ = vinculos.get_or_create(
                account_id=cupom.account_id, platform="shopify", entity_type="cupons",
                external_id=shopify["id"],
                defaults={"object_id": str(cupom.pk), "origin": "shopify"})
        if ref is None:
            continue
        vinculos.filter(pk=ref.pk).update(metadata={**(ref.metadata or {}), **shopify})
        resto = {k: v for k, v in cupom.metadata.items() if k != "shopify"}
        # update(): a migration nao pode disparar save/signal (historico, eco ao Shopify).
        Cupom._base_manager.filter(pk=cupom.pk).update(metadata=resto)


def para_o_cupom(apps, schema_editor):
    Cupom = apps.get_model("loja", "Cupom")
    for ref in _vinculos(apps).filter(platform="shopify", entity_type="cupons"):
        cupom = Cupom._base_manager.filter(pk=ref.object_id).first()
        if cupom is None or not ref.metadata:
            continue
        Cupom._base_manager.filter(pk=cupom.pk).update(
            metadata={**(cupom.metadata or {}), "shopify": ref.metadata})


class Migration(migrations.Migration):
    dependencies = [
        ("loja", "0008_cupom_nome_unico"),
        ("core", "0003_grupos_e_perfis_padrao"),
    ]
    operations = [migrations.RunPython(para_o_vinculo, para_o_cupom)]
