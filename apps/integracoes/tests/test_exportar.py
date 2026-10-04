import pytest

from apps.core import origem
from apps.core.models import ExternalReference
from apps.integracoes.envio.base import EnviadorRecurso
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.tasks import exportar_dados
from apps.loja.models import Categoria, Pedido, Produto, VarianteProduto

from .envio_falso import ApiFora, MarketplaceFalso, ProdutoFalso, chamadas, configuracao


def _exportar(config, recursos):
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.EXPORTAR,
        parametros={"direcao": "exportar", "recursos": recursos},
    )
    resultado = exportar_dados.run(str(execucao.pk))
    execucao.refresh_from_db()
    return resultado, execucao


def _vincular(config, produto, external_id):
    ExternalReference.objects.create(
        platform=config.plataforma, entity_type="produtos",
        object_id=str(produto.pk), external_id=external_id,
    )


@pytest.mark.django_db
def test_exportar_cria_os_novos_e_atualiza_os_vinculados(falsos):
    """Mandar create para produto ja vinculado duplicaria o produto no marketplace."""
    config = configuracao("falso")
    novo = Produto.objects.create(nome="Camiseta")
    antigo = Produto.objects.create(nome="Bone")
    _vincular(config, antigo, "falso-antigo")

    resultado, execucao = _exportar(config, ["produtos"])

    assert sorted(falsos, key=str) == sorted(
        [("falso", "criar", novo.pk), ("falso", "atualizar", "falso-antigo")], key=str
    )
    assert resultado["status"] == "completed"
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA
    assert execucao.mensagem == "2 enviados, 0 ignorados"
    assert (execucao.processados, execucao.total, execucao.progresso) == (2, 2, 100)


@pytest.mark.django_db
def test_exportar_com_so_atualizar_ligado_nao_cria_e_atualiza_os_vinculados(falsos):
    """Mandar tudo como create barrava o vinculado quando so 'atualizar' esta ligado."""
    config = configuracao("falso", recursos=())
    config.permissoes = {"enviar": {"produtos": {"update": True}}}
    config.save()
    Produto.objects.create(nome="Camiseta")
    antigo = Produto.objects.create(nome="Bone")
    _vincular(config, antigo, "falso-antigo")

    _resultado, execucao = _exportar(config, ["produtos"])

    assert falsos == [("falso", "atualizar", "falso-antigo")]
    assert execucao.mensagem == "1 enviados, 1 ignorados"


@pytest.mark.django_db
def test_exportar_segue_depois_de_uma_falha_e_lista_os_ids(falsos, monkeypatch):
    """Um produto com erro na API parava a exportacao da loja inteira."""
    config = configuracao("falso")
    produtos = [Produto.objects.create(nome=f"P{i}") for i in range(3)]
    ruim = produtos[1]
    criar = ProdutoFalso.criar

    def criar_com_falha(self, obj):
        if obj.pk == ruim.pk:
            raise ApiFora("422 titulo invalido")
        return criar(self, obj)

    monkeypatch.setattr(ProdutoFalso, "criar", criar_com_falha)

    _resultado, execucao = _exportar(config, ["produtos"])

    assert len(falsos) == 2
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
    assert execucao.mensagem.startswith(f"2 enviados, 0 ignorados, 1 falharam: produtos {ruim.pk}")
    assert "422 titulo invalido" in execucao.mensagem


@pytest.mark.django_db
def test_exportar_conta_nao_suportado_como_ignorado_e_respeita_a_ordem(falsos, monkeypatch):
    """Categoria que o marketplace nao cria nao e falha; e vai antes do produto."""
    config = configuracao("falso")
    Categoria.objects.create(nome="Verao", slug="verao")
    Produto.objects.create(nome="Camiseta")
    ordem = []
    enviar = MarketplaceFalso.enviar

    def registrar(self, recurso, operacao, pk):
        ordem.append(recurso)
        return enviar(self, recurso, operacao, pk)

    monkeypatch.setattr(MarketplaceFalso, "enviar", registrar)

    _resultado, execucao = _exportar(config, ["produtos", "categorias"])

    assert execucao.mensagem == "1 enviados, 1 ignorados"
    assert ordem == ["categorias", "produtos"]


@pytest.mark.django_db
def test_exportar_so_os_recursos_pedidos(falsos):
    """Exportar produtos nao pode mexer em categoria que o operador nao escolheu."""
    config = configuracao("falso")
    Categoria.objects.create(nome="Verao", slug="verao")

    _resultado, execucao = _exportar(config, ["produtos"])

    assert falsos == []
    assert execucao.mensagem == "0 enviados, 0 ignorados"


@pytest.mark.django_db
def test_exportar_roda_com_a_origem_do_destino(falsos, monkeypatch):
    """Vinculo gravado pela exportacao nao pode voltar como alteracao para o mesmo marketplace."""
    config = configuracao("falso")
    Produto.objects.create(nome="Camiseta")
    vista = []
    monkeypatch.setattr(
        ProdutoFalso, "criar", lambda self, obj: vista.append(origem.atual()) or "x"
    )

    _exportar(config, ["produtos"])

    assert vista == ["falso"]


@pytest.mark.django_db
def test_exportar_sem_marketplace_registrado_falha_com_motivo(falsos):
    """Plataforma sem enviador deixava a tarefa pendente sem explicar nada."""
    config = configuracao("sem_enviador", recursos=())

    resultado, execucao = _exportar(config, ["produtos"])

    assert resultado["status"] == "failed"
    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert "ainda nao envia dados para sem_enviador" in execucao.mensagem


@pytest.mark.django_db
def test_exportar_estoque_so_das_variantes_que_controlam_estoque(falsos):
    """Variante sem controle de estoque zeraria a quantidade no marketplace."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Camiseta")
    controla = VarianteProduto.objects.create(produto=produto, sku="A", inventory_quantity=5)
    VarianteProduto.objects.create(produto=produto, sku="B", manage_inventory=False)
    ExternalReference.objects.create(
        platform="falso", entity_type="variantes", object_id=str(controla.pk), external_id="v1",
    )

    _resultado, execucao = _exportar(config, ["estoque"])

    assert ("falso", "estoque", 5) in falsos
    controladas = VarianteProduto.objects.filter(manage_inventory=True).count()
    assert VarianteProduto.objects.count() == controladas + 1
    assert execucao.total == controladas


class PedidoFalso(EnviadorRecurso):
    recurso = "pedidos"
    modelo = Pedido

    def atualizar(self, obj, external_id):
        chamadas.append(("falso", "pedido", external_id))


@pytest.mark.django_db
def test_exportar_pedidos_so_atualiza_os_ja_vinculados(falsos, monkeypatch):
    """Pedido nasce no marketplace: exportar nao pode criar pedido do hub la."""
    monkeypatch.setattr(MarketplaceFalso, "recursos", (*MarketplaceFalso.recursos, PedidoFalso))
    config = configuracao("falso", recursos=("pedidos",))
    vinculado = Pedido.objects.create()
    Pedido.objects.create()
    ExternalReference.objects.create(
        platform="falso", entity_type="pedidos", object_id=str(vinculado.pk), external_id="p1",
    )

    _resultado, execucao = _exportar(config, ["pedidos"])

    assert falsos == [("falso", "pedido", "p1")]
    assert execucao.mensagem == "1 enviados, 0 ignorados"
