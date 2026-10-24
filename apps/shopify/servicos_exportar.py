"""Exportar todos os servicos para a Shopify (botao em Loja > Servicos) e a barreira
que impede o produto-servico de virar Produto do catalogo.

O cadastro dos servicos vem do hub (tela ou planilha, apps/loja/services/
servicos_planilha.py); a Shopify so recebe. eh_servico e usado pela importacao de
produtos, pelos webhooks e pelo produto faltante do pedido.
"""

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Servico
from apps.shopify.servicos_envio import TAG


def eh_servico(dados):
    tags = (dados or {}).get("tags") or []
    if isinstance(tags, str):  # corpo REST do webhook: "a, b"
        tags = [t.strip() for t in tags.split(",")]
    if TAG in tags:
        return True
    return ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="servicos",
        external_id=str((dados or {}).get("id") or "")).exists()


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
