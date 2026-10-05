"""Webhook de pedidos, cadastro do webhook e Sincronizar loja do Suri Shop."""

import json

import pytest
from django.urls import reverse

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import argumentos
from apps.loja.models import Categoria, Pedido, Produto
from apps.suri.tasks import sincronizar_suri
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido, produto
from apps.suri.webhooks import cadastrar_webhooks, id_do_pedido

pytestmark = pytest.mark.django_db
PEDIDOS = (("pedidos", "create"), ("pedidos", "update"))


def _postar(client, cfg, corpo):
    url = reverse("suri_webhook", args=[cfg.uuid])
    return client.post(url, json.dumps(corpo), content_type="application/json")


@pytest.mark.parametrize("corpo", [
    {"id": "51807"}, {"orderId": "51807"}, {"order": {"id": "51807"}},
    {"type": "order", "payload": {"order": {"id": 51807}}}])
def test_id_do_pedido_sai_dos_formatos_possiveis(corpo):
    assert id_do_pedido(corpo) == "51807"


def test_webhook_rele_o_pedido_na_api_e_ignora_o_corpo(client, conta, monkeypatch):
    """O Suri nao assina: o corpo forjado nao pode virar pedido, so o id e usado."""
    loja = SuriFalso(produtos=[produto()], pedidos=[pedido()]).instalar(monkeypatch)
    cfg = configuracao(conta, receber=PEDIDOS)

    resposta = _postar(client, cfg, {"id": "51807", "totalAmount": 1, "items": []})

    assert resposta.status_code == 202
    assert ("GET", "shop/orders/51807", None) in loja.chamadas
    assert Pedido.objects.get().total == pedido()["totalAmount"]
    assert ExecucaoIntegracao.objects.get().status == ExecucaoIntegracao.Status.CONCLUIDA


def test_webhook_sem_pedido_ou_desligado_nao_cria_tarefa(client, conta):
    ligado = configuracao(conta, receber=PEDIDOS)

    sem_id = _postar(client, ligado, {"type": "new-contact"})
    ligado.permissoes = {}
    ligado.save()
    desligado = _postar(client, ligado, {"id": "51807"})

    assert (sem_id.status_code, desligado.status_code) == (204, 204)
    assert not ExecucaoIntegracao.objects.exists()


def test_get_do_teste_de_endereco_responde_200(client, conta):
    cfg = configuracao(conta, receber=PEDIDOS)

    assert client.get(reverse("suri_webhook", args=[cfg.uuid])).status_code == 200


def test_cadastro_define_o_endereco_com_o_uuid(conta, monkeypatch):
    loja = SuriFalso().instalar(monkeypatch)
    cfg = configuracao(conta, receber=PEDIDOS)

    cadastrar_webhooks(cfg, lambda *_: None)

    assert loja.chamadas == [("POST", "shop/hook", {
        "url": f"https://hub.test/integracoes/suri/webhook/{cfg.uuid}/"})]


def test_sincronizacao_importa_categorias_produtos_e_pedidos(conta, monkeypatch):
    SuriFalso(produtos=[produto()], pedidos=[pedido(), pedido(id="9", status=0)],
              categorias=[{"id": "48348", "name": "Roupas", "children": []}]
              ).instalar(monkeypatch)
    cfg = configuracao(conta, receber=[(r, "get") for r in ("categorias", "produtos",
                                                              "pedidos")])
    execucao = ExecucaoIntegracao.objects.create(configuracao=cfg,
                                                 tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR)

    resultado = sincronizar_suri(str(execucao.pk))

    execucao.refresh_from_db()
    assert resultado["status"] == ExecucaoIntegracao.Status.CONCLUIDA, execucao.falhas
    assert execucao.progresso == 100
    assert Categoria.objects.count() == 1 and Produto.objects.count() == 1
    assert Pedido.objects.count() == 1, "o carrinho (status 0) nao entra"


def test_retomar_usa_as_tarefas_do_suri(conta):
    execucao = ExecucaoIntegracao.objects.create(configuracao=configuracao(conta),
                                                 tipo=ExecucaoIntegracao.Tipo.RECEBER,
                                                 parametros={"reenvio": {
                                                     "recurso": "pedidos", "operacao": "update",
                                                     "dados": {"id": "51807"}}})

    caminho, args, _ = argumentos(execucao)

    assert caminho == "apps.suri.tasks.processar_webhook_suri"
    assert args[1:] == ("pedidos", "update", {"id": "51807"})
