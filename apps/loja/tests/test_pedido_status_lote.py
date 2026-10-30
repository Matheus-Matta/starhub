"""Acao "Mudar status para ..." na lista de pedidos."""

import pytest

from apps.loja.models import Pedido


def _acao(admin_logado, status, pedidos):
    return admin_logado.post("/admin/loja/pedido/", {
        "action": f"status_{status.replace('-', '_')}",
        "_selected_action": [p.pk for p in pedidos],
    }, follow=True)


@pytest.mark.django_db
def test_acao_muda_o_status_dos_selecionados_e_marca_as_datas_como_a_api(admin_logado):
    """Concluido sem data de conclusao chegava ao ERP com date_completed vazio."""
    um, dois = Pedido.objects.create(number="A1"), Pedido.objects.create(number="A2")
    fora = Pedido.objects.create(number="A3")

    resposta = _acao(admin_logado, Pedido.Status.CONCLUIDO, [um, dois])

    assert "2 pedido(s) agora com status Concluido." in resposta.content.decode()
    for pedido in (um, dois):
        pedido.refresh_from_db()
        assert pedido.status == Pedido.Status.CONCLUIDO
        assert pedido.fulfilled_at and pedido.paid_at
        assert pedido.financial_status == Pedido.StatusFinanceiro.PAGO
    fora.refresh_from_db()
    assert fora.status == Pedido.Status.PENDENTE


@pytest.mark.django_db
def test_acao_passa_pelo_save_e_pula_quem_ja_estava_no_status(admin_logado, monkeypatch):
    """update() pularia o post_save: StarChats e o envio as lojas nao saberiam da mudanca."""
    from django.db.models.signals import post_save

    salvos = []

    def contar(sender, instance, **kwargs):
        salvos.append(instance.pk)

    post_save.connect(contar, sender=Pedido, dispatch_uid="teste_status_lote")
    try:
        cancelado = Pedido.objects.create(number="B1", status=Pedido.Status.CANCELADO)
        pendente = Pedido.objects.create(number="B2")
        salvos.clear()
        resposta = _acao(admin_logado, Pedido.Status.CANCELADO, [cancelado, pendente])
    finally:
        post_save.disconnect(dispatch_uid="teste_status_lote", sender=Pedido)

    assert salvos == [pendente.pk]
    pendente.refresh_from_db()
    assert pendente.cancelled_at is not None
    assert "1 ja estava(m) assim" in resposta.content.decode()
