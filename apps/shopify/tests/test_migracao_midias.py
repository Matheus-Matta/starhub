"""Migration que tira os dados do Shopify do metadados da midia e poe no vinculo."""

import importlib

import pytest
from django.apps import apps

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto, Produto

migracao = importlib.import_module("apps.shopify.migrations.0001_midias_no_vinculo")
CDN = "https://cdn.shopify.com/s/files/1/x.png?v=1"


@pytest.mark.django_db
def test_move_para_o_vinculo_e_volta_sem_perder_as_copias(conta):
    """Foto importada antes da mudanca sem vinculo seria baixada de novo no proximo webhook."""
    produto = Produto.objects.create(nome="Mesa")
    antigo = {"shopify_image_id": "gid://shopify/ProductImage/5", "shopify_src": CDN}
    primeira = MidiaProduto.objects.create(produto=produto, url="/media/x.png",
                                           metadados={**antigo, "outro": 1})
    copia = MidiaProduto.objects.create(produto=produto, url="/media/x.png", metadados=antigo)

    migracao.mover_para_o_vinculo(apps, None)

    vinculo = ExternalReference.objects.get(entity_type="midias")
    assert vinculo.object_id == str(primeira.pk)
    assert vinculo.external_id == antigo["shopify_image_id"]
    assert vinculo.metadata == {"shopify_src": CDN}
    primeira.refresh_from_db()
    copia.refresh_from_db()
    assert primeira.metadados == {"outro": 1} and copia.metadados == []

    migracao.voltar_para_a_midia(apps, None)

    primeira.refresh_from_db()
    copia.refresh_from_db()
    assert primeira.metadados == {**antigo, "outro": 1} and copia.metadados == antigo
    assert not ExternalReference.objects.filter(entity_type="midias").exists()
