"""Numeros do painel inicial do admin (templates/admin/index.html)."""

from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.loja.dinheiro import ZERO
from apps.loja.models import Cliente, Pedido, Produto, VarianteProduto

# Sem estoque minimo cadastrado, avisa a partir desta quantidade.
ESTOQUE_BAIXO_PADRAO = 5


def _estoque_baixo():
    """Variantes (a unidade vendida) no limite: SKU a SKU, nao o produto inteiro."""
    limite = Q(
        low_stock_amount__isnull=False, inventory_quantity__lte=F("low_stock_amount")
    ) | Q(low_stock_amount__isnull=True, inventory_quantity__lte=ESTOQUE_BAIXO_PADRAO)
    return (
        VarianteProduto.objects.filter(manage_inventory=True, active=True)
        .exclude(produto__status=Produto.Status.LIXEIRA)
        .filter(limite)
        .select_related("produto")
        .order_by("inventory_quantity", "produto__nome")
    )


def montar_painel():
    inicio_mes = timezone.localdate().replace(day=1)
    pedidos_mes = Pedido.objects.filter(created_at__date__gte=inicio_mes).exclude(
        status=Pedido.Status.LIXEIRA
    )
    receita_mes = (
        pedidos_mes.filter(status__in=Pedido.PAGOS).aggregate(soma=Sum("total"))["soma"] or ZERO
    )
    por_status = dict(
        Pedido.objects.exclude(status=Pedido.Status.LIXEIRA)
        .values_list("status")
        .annotate(qtd=Count("id"))
    )
    estoque_baixo = _estoque_baixo()
    return {
        "indicadores": [
            {
                "rotulo": "Receita do mes",
                "valor": receita_mes,
                "eh_moeda": True,
                "icone": "wallet",
                "tom": "success",
                "detalhe": "pedidos processando ou concluidos",
            },
            {
                "rotulo": "Pedidos no mes",
                "valor": pedidos_mes.count(),
                "icone": "shopping-cart",
                "tom": "primary",
                "detalhe": f"{por_status.get('processing', 0)} processando agora",
            },
            {
                "rotulo": "Produtos ativos",
                "valor": Produto.objects.filter(status=Produto.Status.PUBLICADO).count(),
                "icone": "package",
                "tom": "info",
                "detalhe": f"{estoque_baixo.count()} com estoque baixo",
            },
            {
                "rotulo": "Clientes",
                "valor": Cliente.objects.count(),
                "icone": "users-round",
                "tom": "warning",
                "detalhe": "cadastrados no hub",
            },
        ],
        "status_pedidos": [
            {"valor": valor, "rotulo": rotulo, "qtd": por_status.get(valor, 0)}
            for valor, rotulo in Pedido.Status.choices
            if valor not in (Pedido.Status.LIXEIRA, Pedido.Status.RASCUNHO)
        ],
        "pedidos_recentes": Pedido.objects.select_related("cliente")
        .exclude(status=Pedido.Status.LIXEIRA)
        .order_by("-created_at")[:6],
        "estoque_baixo": estoque_baixo[:6],
    }
