"""O envio de imagens pela tarefa nao gera eco de volta para o Shopify."""

from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.integracoes.tasks import enviar_alteracao
from apps.loja.models import MidiaProduto
from apps.shopify.tests.test_envio_midias import HUB, LOCAL, PROCESSANDO, _set
from apps.shopify.tests.test_envio_produtos import ClienteFalso, _simples


@pytest.mark.django_db
def test_gravacoes_do_envio_rodam_como_shopify_e_nao_agendam_novo_envio(
    conta, monkeypatch, django_capture_on_commit_callbacks
):
    """Se o vinculo da midia ou o produto gravados no envio agendassem outro envio,
    o hub mandaria a mesma foto ao Shopify num laco sem fim."""
    agendados = []
    monkeypatch.setattr(
        "apps.integracoes.envio.distribuidor._enfileirar",
        lambda *args: agendados.append(args),
    )
    matriz = permissoes.matriz_vazia()
    matriz["enviar"]["produtos"]["create"] = matriz["enviar"]["produtos"]["update"] = True
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=matriz
    )
    produto, _ = _simples()
    midia = MidiaProduto.objects.create(produto=produto, url=HUB)
    alterado_em = produto.updated_at
    cliente = ClienteFalso({"location": {"location": LOCAL}, "productSet": _set(77),
                            **PROCESSANDO})

    with (
        patch("apps.shopify.envio.base.ShopifyClient", return_value=cliente),
        django_capture_on_commit_callbacks(execute=True),
    ):
        enviar_alteracao.run(str(configuracao.pk), "produtos", "create", str(produto.pk))

    assert ExternalReference.objects.filter(entity_type="midias", object_id=str(midia.pk)).exists()
    assert agendados == []
    produto.refresh_from_db()
    assert produto.updated_at == alterado_em
