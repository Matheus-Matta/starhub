"""Servicos da Shopify -> cadastro de Servicos do hub (botao "Importar da Shopify").

Os produtos da loja com a tag `starhub-servico` (os que o hub exportou e os que o
lojista criou la) viram Servico: nome, SKU da primeira variante e o menor preco como
preco padrao. Servico ja vinculado ou com o mesmo SKU e atualizado, nunca duplicado.
O produto-servico nunca vira Produto do catalogo (eh_servico, usado pela importacao
de produtos e pelos webhooks).
"""

from decimal import Decimal

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Servico
from apps.shopify.cliente import ShopifyClient
from apps.shopify.envio.produtos_variantes import dinheiro
from apps.shopify.servicos_envio import TAG, VARIANTES

CONSULTA = """query($cursor: String) {
  products(first: 50, after: $cursor, query: "tag:'starhub-servico'") {
    nodes { id title status tags variants(first: 100) { nodes { id sku price } } }
    pageInfo { hasNextPage endCursor }
  }
}"""


def eh_servico(dados):
    tags = (dados or {}).get("tags") or []
    if isinstance(tags, str):  # corpo REST do webhook: "a, b"
        tags = [t.strip() for t in tags.split(",")]
    if TAG in tags:
        return True
    return ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="servicos",
        external_id=str((dados or {}).get("id") or "")).exists()


def _produtos(cliente):
    cursor = None
    while True:
        conexao = cliente.graphql(CONSULTA, {"cursor": cursor})["products"]
        yield from conexao.get("nodes") or []
        if not (conexao.get("pageInfo") or {}).get("hasNextPage"):
            return
        cursor = conexao["pageInfo"]["endCursor"]


def _vincular(entidade, externo, servico, pai="", metadata=None):
    ExternalReference.objects.update_or_create(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id=externo,
        defaults={"object_id": str(servico.pk), "external_parent_id": pai,
                  "metadata": metadata or {}, "origin": Origin.SHOPIFY})


def importar_servico(dados):
    """(servico, criado) de um produto-servico da Shopify."""
    variantes = (dados.get("variants") or {}).get("nodes") or []
    sku = next((str(v.get("sku") or "").strip() for v in variantes if v.get("sku")), "")
    precos = [Decimal(str(v["price"])) for v in variantes if v.get("price") not in (None, "")]
    referencia = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="servicos", external_id=dados["id"]).first()
    servico = Servico.objects.filter(pk=referencia.object_id).first() if referencia else None
    servico = servico or (Servico.objects.filter(sku=sku).first() if sku else None)
    criado = servico is None
    servico = servico or Servico(origin=Origin.SHOPIFY)
    servico.nome = (dados.get("title") or servico.nome or "Servico Shopify")[:150]
    servico.sku = sku or servico.sku
    servico.preco = min(precos) if precos else servico.preco
    servico.active = dados.get("status", "ACTIVE") == "ACTIVE"
    servico.save()
    _vincular("servicos", dados["id"], servico)
    for variante in variantes:
        preco = dinheiro(Decimal(str(variante["price"]))) if variante.get("price") else None
        _vincular(VARIANTES, variante["id"], servico, pai=dados["id"],
                  metadata={"preco": preco})
    return servico, criado


def importar_servicos(configuracao, progresso):
    lidos = criados = 0
    for dados in _produtos(ShopifyClient(configuracao)):
        _servico, novo = importar_servico(dados)
        lidos, criados = lidos + 1, criados + int(novo)
        progresso(lidos, lidos, f"Servicos: {lidos} lidos")
    return f"{lidos} servicos lidos na Shopify; {criados} novos no hub."


def exportar_servicos(configuracao, progresso):
    """Todos os servicos da conta para a Shopify; um que falha vira aviso e os outros
    seguem. Mesmo caminho do envio automatico (servicos_sinais.py)."""
    from apps.integracoes.falhas import motivo_legivel
    from apps.shopify.contexto import avisar
    from apps.shopify.envio.marketplace import ShopifyMarketplace

    marketplace = ShopifyMarketplace(configuracao)
    if not marketplace.habilitado("servicos", "create"):
        raise ValueError("Ligue \"enviar servicos\" em Integracoes > Shopify > Servicos e "
                         "salve antes de exportar.")
    servicos = list(Servico.objects.order_by("nome"))
    enviados = 0
    for posicao, servico in enumerate(servicos, 1):
        try:
            marketplace.enviar("servicos", "update", servico.pk)
            enviados += 1
        except Exception as erro:  # noqa: BLE001 - um servico ruim nao para os outros
            avisar(motivo_legivel(erro), recurso="servicos", id=servico.pk,
                   descricao=f"{servico.nome} ({servico.sku})")
        progresso(posicao, len(servicos), f"Servicos: {posicao}/{len(servicos)}")
    return f"{enviados} de {len(servicos)} servicos enviados a Shopify."
