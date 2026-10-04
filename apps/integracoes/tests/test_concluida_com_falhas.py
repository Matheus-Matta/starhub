"""Exportacao em lote com parte dos itens com erro: status proprio e lista legivel."""

import pytest
from django.db import IntegrityError

from apps.core.models import ExternalReference
from apps.integracoes.falhas import motivo_legivel
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.tasks import exportar_dados
from apps.loja.models import Produto

from .envio_falso import ApiFora, ProdutoFalso, configuracao

COM_FALHAS = ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS


def _exportar(config, recursos):
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.EXPORTAR,
        parametros={"direcao": "exportar", "recursos": recursos},
    )
    resultado = exportar_dados.run(str(execucao.pk))
    execucao.refresh_from_db()
    return resultado, execucao


def _falhar_em(monkeypatch, ruins, erro=None):
    criar, atualizar = ProdutoFalso.criar, ProdutoFalso.atualizar
    pks = {obj.pk for obj in ruins}

    def criar_ou_falhar(self, obj):
        if obj.pk in pks:
            raise erro or ApiFora("422 titulo invalido")
        return criar(self, obj)

    def atualizar_ou_falhar(self, obj, external_id):
        if obj.pk in pks:
            raise erro or ApiFora("422 titulo invalido")
        return atualizar(self, obj, external_id)

    monkeypatch.setattr(ProdutoFalso, "criar", criar_ou_falhar)
    monkeypatch.setattr(ProdutoFalso, "atualizar", atualizar_ou_falhar)


@pytest.mark.django_db
def test_exportar_com_parte_dos_itens_com_erro_fica_concluida_com_falhas(falsos, monkeypatch):
    """Com um item com erro a tarefa saia "Concluida" e o operador nao via o problema."""
    config = configuracao("falso")
    Produto.objects.create(nome="Bone")
    ruim = Produto.objects.create(nome="Camiseta")
    _falhar_em(monkeypatch, [ruim])

    resultado, execucao = _exportar(config, ["produtos"])

    assert execucao.status == COM_FALHAS
    assert resultado["status"] == COM_FALHAS
    assert execucao.falhas == [{
        "recurso": "produtos", "id": str(ruim.pk), "descricao": "Camiseta",
        "id_externo": "", "motivo": "422 titulo invalido",
    }]
    assert "1 enviados" in execucao.mensagem and "1 falharam" in execucao.mensagem
    assert "exporte de novo" in execucao.mensagem


@pytest.mark.django_db
def test_exportar_falha_traz_o_id_externo_do_item_ja_vinculado(falsos, monkeypatch):
    """Sem o id externo o operador nao acha o item no marketplace para corrigir."""
    config = configuracao("falso")
    Produto.objects.create(nome="Bone")
    ruim = Produto.objects.create(nome="Camiseta")
    ExternalReference.objects.create(
        platform="falso", entity_type="produtos", object_id=str(ruim.pk), external_id="ext-9",
    )
    _falhar_em(monkeypatch, [ruim])

    _resultado, execucao = _exportar(config, ["produtos"])

    assert execucao.falhas[0]["id_externo"] == "ext-9"


@pytest.mark.django_db
def test_exportar_com_todos_os_itens_com_erro_continua_falhou(falsos, monkeypatch):
    """Nada enviado nao e "concluida": continua FALHOU, mas com a lista do que deu erro."""
    config = configuracao("falso")
    produtos = [Produto.objects.create(nome=f"P{i}") for i in range(2)]
    _falhar_em(monkeypatch, produtos)

    _resultado, execucao = _exportar(config, ["produtos"])

    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert [f["id"] for f in execucao.falhas] == [str(p.pk) for p in produtos]


@pytest.mark.django_db
def test_exportar_traduz_erro_conhecido_no_motivo(falsos, monkeypatch):
    """IntegrityError cru ("UNIQUE constraint failed") nao diz ao operador o que fazer."""
    config = configuracao("falso")
    Produto.objects.create(nome="Bone")
    ruim = Produto.objects.create(nome="Camiseta")
    _falhar_em(monkeypatch, [ruim], IntegrityError("UNIQUE constraint failed: sku"))

    _resultado, execucao = _exportar(config, ["produtos"])

    assert execucao.falhas[0]["motivo"].startswith("Ja existe outro registro")


@pytest.mark.parametrize(("erro", "inicio"), [
    (RuntimeError("Shopify respondeu HTTP 401: x"), "O marketplace recusou as credenciais"),
    (RuntimeError("Shopify respondeu HTTP 429: x"), "O marketplace limitou"),
    (TimeoutError("timed out"), "O marketplace nao respondeu"),
    (RuntimeError(""), "RuntimeError"),
])
def test_motivo_legivel_explica_o_que_fazer(erro, inicio):
    """Codigo HTTP cru nao diz ao operador se e credencial, limite ou rede."""
    assert motivo_legivel(erro).startswith(inicio)
