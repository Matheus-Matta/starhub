"""O lock da linha canonica so existe para nao criar duas vezes no marketplace."""

import pytest

from apps.integracoes.envio.base import EnviadorRecurso
from apps.integracoes.tests.envio_falso import MarketplaceFalso, configuracao
from apps.loja.models import Produto


def _espiar_lock(monkeypatch, antes_de_devolver=None):
    chamadas = []
    original = EnviadorRecurso._carregar_travado

    def travado(self, pk):
        chamadas.append(pk)
        if antes_de_devolver:
            antes_de_devolver(self)
        return original(self, pk)

    monkeypatch.setattr(EnviadorRecurso, "_carregar_travado", travado)
    return chamadas


@pytest.mark.django_db
def test_update_com_vinculo_nao_trava_a_linha(falsos, monkeypatch):
    """Com lock, a baixa de estoque do pedido esperava o timeout do Shopify (30s)."""
    produto = Produto.objects.create(nome="Camiseta")
    enviador = MarketplaceFalso(configuracao("falso")).enviador("produtos")
    enviador.vincular(produto, "falso-1")
    travas = _espiar_lock(monkeypatch)

    assert enviador.enviar("update", produto.pk) == "atualizado"
    assert travas == []
    assert falsos == [("falso", "atualizar", "falso-1")]


@pytest.mark.django_db
def test_criar_trava_a_linha(falsos, monkeypatch):
    """Sem lock, create e update em workers diferentes criavam dois produtos no marketplace."""
    produto = Produto.objects.create(nome="Camiseta")
    enviador = MarketplaceFalso(configuracao("falso")).enviador("produtos")
    travas = _espiar_lock(monkeypatch)

    assert enviador.enviar("create", produto.pk) == f"criado falso-{produto.pk}"
    assert travas == [produto.pk]


@pytest.mark.django_db
def test_vinculo_gravado_por_outro_envio_durante_o_lock_vira_atualizar(falsos, monkeypatch):
    """Sem reler depois do lock, o segundo envio criava de novo o que o primeiro ja criou."""
    produto = Produto.objects.create(nome="Camiseta")
    enviador = MarketplaceFalso(configuracao("falso")).enviador("produtos")
    # Simula o outro worker gravando o vinculo enquanto este esperava o lock.
    _espiar_lock(monkeypatch, lambda self: self.vincular(produto, "do-outro"))

    assert enviador.enviar("create", produto.pk) == "atualizado"
    assert falsos == [("falso", "atualizar", "do-outro")]
