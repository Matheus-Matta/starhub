"""Move os dados do Shopify do metadados da MidiaProduto para o vinculo "midias".

Antes a importacao gravava `shopify_image_id` e `shopify_src` no proprio registro
do hub; agora cada marketplace guarda os seus no ExternalReference dele. Sem mover,
as fotos ja importadas nao seriam reconhecidas e o proximo webhook baixaria de novo.
"""

from django.db import migrations

CHAVES = ("shopify_image_id", "shopify_src")


def mover_para_o_vinculo(apps, schema_editor):
    MidiaProduto = apps.get_model("loja", "MidiaProduto")
    ExternalReference = apps.get_model("core", "ExternalReference")
    for midia in MidiaProduto._base_manager.exclude(metadados=[]).iterator():
        meta = midia.metadados if isinstance(midia.metadados, dict) else {}
        externo = meta.get("shopify_image_id")
        if not externo:
            continue
        # Copias da mesma foto (uma por variante) dividem o id: o primeiro vira o
        # vinculo e as demais sao reconhecidas pela mesma URL local (imagens.py).
        ExternalReference._base_manager.get_or_create(
            account_id=midia.account_id, platform="shopify", entity_type="midias",
            external_id=externo,
            defaults={"object_id": str(midia.pk), "origin": "shopify",
                      "metadata": {"shopify_src": meta.get("shopify_src") or ""}},
        )
        resto = {k: v for k, v in meta.items() if k not in CHAVES}
        midia.metadados = resto or []
        midia.save(update_fields=["metadados"])


def voltar_para_a_midia(apps, schema_editor):
    MidiaProduto = apps.get_model("loja", "MidiaProduto")
    ExternalReference = apps.get_model("core", "ExternalReference")
    vinculos = ExternalReference._base_manager.filter(platform="shopify", entity_type="midias")
    for vinculo in vinculos.iterator():
        src = (vinculo.metadata or {}).get("shopify_src")
        midia = MidiaProduto._base_manager.filter(pk=vinculo.object_id).first()
        if midia is None or not src or (vinculo.metadata or {}).get("enviado_src"):
            continue
        copias = MidiaProduto._base_manager.filter(produto_id=midia.produto_id, url=midia.url)
        for copia in copias:
            meta = copia.metadados if isinstance(copia.metadados, dict) else {}
            copia.metadados = {**meta, "shopify_image_id": vinculo.external_id,
                               "shopify_src": src}
            copia.save(update_fields=["metadados"])
    vinculos.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_grupos_e_perfis_padrao"),
        ("loja", "0008_cupom_nome_unico"),
    ]

    operations = [migrations.RunPython(mover_para_o_vinculo, voltar_para_a_midia)]
