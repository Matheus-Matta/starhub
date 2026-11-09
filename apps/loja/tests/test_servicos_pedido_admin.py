"""Card "Servicos do pedido" na tela do admin: POST da pagina inteira, como o navegador.

As regras de valor (somado, diferenca, versao) estao em test_servicos_pedido_tela.py.
"""

import json
from decimal import Decimal
from html.parser import HTMLParser

import pytest

from apps.loja.models import ItemPedido, Pedido
from apps.loja.tests.test_servicos_pedido_tela import (
    _orfao,
    _servicos,
    _totais,
    criar_pedido_com_servicos,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(conta):
    return criar_pedido_com_servicos()


class _Campos(HTMLParser):
    """Campos do formulario como o navegador mandaria (input, textarea, select)."""

    def __init__(self):
        super().__init__()
        self.dados, self._texto, self._select = {}, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        nome = a.get("name")
        if tag == "input" and nome and a.get("type") not in ("submit", "button", "file"):
            if a.get("type") in ("checkbox", "radio") and "checked" not in a:
                return
            self.dados[nome] = a.get("value", "on" if a.get("type") == "checkbox" else "")
        elif tag == "textarea" and nome:
            self._texto, self.dados[nome] = nome, ""
        elif tag == "select" and nome:
            self._select = nome
        elif tag == "option" and self._select and "selected" in a:
            self.dados[self._select] = a.get("value", "")

    def handle_endtag(self, tag):
        if tag == "textarea":
            self._texto = None
        elif tag == "select":
            self._select = None

    def handle_data(self, data):
        if self._texto:
            self.dados[self._texto] += data


def test_tela_do_pedido_edita_os_servicos(admin_logado, pedido):
    obj, _, mesa, montagem, _ = pedido
    url = f"/admin/loja/pedido/{obj.pk}/change/"
    html = admin_logado.get(url).content.decode()
    campos = _Campos()
    campos.feed(html)
    linhas = json.loads(campos.dados["servicos_do_pedido"])
    linhas.append({"item_id": str(mesa.pk), "servico_id": str(montagem.pk),
                   "opcao": "Sim", "preco": "80.00"})

    resposta = admin_logado.post(url, {**campos.dados, "servicos_do_pedido": json.dumps(linhas),
                                       "_save": "Salvar"})

    assert resposta.status_code == 302, resposta.content.decode()[:3000]
    assert _totais(mesa) == [Decimal("380.00")]
    assert len(_servicos(obj)) == 3


def test_tela_nao_salva_pedido_com_servico_sem_item(admin_logado, pedido):
    obj, sofa, *_ = pedido
    _orfao(obj)
    url = f"/admin/loja/pedido/{obj.pk}/change/"
    html = admin_logado.get(url).content.decode()
    campos = _Campos()
    campos.feed(html)

    resposta = admin_logado.post(url, {**campos.dados, "_save": "Salvar"})

    assert resposta.status_code == 200
    assert "Escolha o item do pedido em cada servico" in resposta.content.decode()
    assert "Item removido" not in html and "Escolha o item" in html


def test_linha_nova_comeca_sem_item_escolhido(pedido):
    """O select abria no primeiro item: o servico novo ia para o sofa sem ninguem escolher."""
    from apps.loja.admin.pedidos_servicos import _colunas

    obj, sofa, *_ = pedido
    opcoes = _colunas(Pedido.objects.get(pk=obj.pk))[0]["opcoes"]

    assert opcoes[0] == {"valor": "", "rotulo": "Escolha o item"}
    assert {"valor": str(sofa.pk), "rotulo": "Sofa (SOF-1)"} in opcoes


def test_excluir_item_com_servico_avisa_para_religar(admin_logado, pedido):
    """O servico da mesa excluida ficava sem item calado; o ERP nao o via mais."""
    obj, _, mesa, *_ = pedido
    url = f"/admin/loja/pedido/{obj.pk}/change/"
    campos = _Campos()
    campos.feed(admin_logado.get(url).content.decode())
    prefixo = next(nome[:-3] for nome, valor in campos.dados.items()
                   if nome.startswith("itens-") and nome.endswith("-id") and valor == str(mesa.pk))

    resposta = admin_logado.post(url, {**campos.dados, f"{prefixo}-DELETE": "on",
                                       "_save": "Salvar"}, follow=True)

    assert not ItemPedido.objects.filter(pk=mesa.pk).exists()
    assert "ficaram sem item" in resposta.content.decode()
