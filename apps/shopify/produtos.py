"""Adapta produto e variantes Shopify ao catalogo canonico do StarHub."""

from decimal import Decimal

from apps.core.models import ExternalReference, Origin
from apps.loja.models import VarianteProduto
from apps.loja.services.variantes import obter_variante_padrao
from apps.shopify.contexto import avisar
from apps.shopify.produtos_opcoes import sincronizar_opcoes


def _precos(dados, decimal):
    atual = decimal(dados.get("price"))
    comparacao = decimal(dados.get("compareAtPrice"))
    regular = comparacao if comparacao > atual else atual
    promocional = atual if comparacao > atual else None
    return regular, promocional, comparacao or None


UNIDADES_PESO = {"KILOGRAMS": "kg", "GRAMS": "g", "POUNDS": "lb", "OUNCES": "oz"}


def _peso(item):
    peso = ((item.get("measurement") or {}).get("weight")) or {}
    if peso.get("value") is None:
        return {}
    # str() antes do Decimal: o Float da GraphQL viraria 2.4999... no Decimal direto.
    valor = Decimal(str(peso["value"])).quantize(Decimal("0.001"))
    return {"weight": valor, "weight_unit": UNIDADES_PESO.get(peso.get("unit"), "kg")}


def _logistica(dados):
    """Campos de entrega/estoque/fiscal da variante que vieram na carga.

    So os presentes: o webhook REST de reserva nao traz inventoryItem nem peso, e
    campo ausente nao pode zerar o que o hub ja tem. GraphQL: tracked/requiresShipping
    ficam em inventoryItem; o REST manda inventory_management/requires_shipping no topo.
    """
    item = dados.get("inventoryItem") or {}
    campos = _peso(item)
    if dados.get("barcode") is not None:
        campos["barcode"] = dados["barcode"]
    if dados.get("taxable") is not None:
        campos["taxable"] = bool(dados["taxable"])
    if dados.get("inventoryPolicy"):
        campos["inventory_policy"] = str(dados["inventoryPolicy"]).lower()
    rastreado = item.get("tracked", dados.get("inventoryManagement"))
    if rastreado is not None:
        campos["manage_inventory"] = bool(rastreado)
    entrega = item.get("requiresShipping", dados.get("requiresShipping"))
    if entrega is not None:
        campos["requires_shipping"] = bool(entrega)
    return campos


def _campos(dados, decimal, posicao):
    regular, promocional, comparacao = _precos(dados, decimal)
    return {
        "titulo": dados.get("title") or "Default",
        "sku": dados.get("sku") or "",
        "barcode": "",
        "price": regular,
        "sale_price": promocional,
        "compare_at_price": comparacao,
        "inventory_quantity": dados.get("inventoryQuantity") or 0,
        "inventory_policy": "deny",
        "manage_inventory": True,
        "taxable": True,
        "requires_shipping": True,
        "posicao": max(int(dados.get("position") or posicao + 1) - 1, 0),
        "origin": Origin.SHOPIFY,
        **_logistica(dados),
    }


def _referenciar_variante(variante, externo_id, produto_externo_id):
    if not externo_id:
        return
    ExternalReference.objects.update_or_create(
        platform=Origin.SHOPIFY,
        entity_type="variantes",
        external_id=externo_id,
        defaults={
            "object_id": str(variante.pk),
            "external_parent_id": produto_externo_id,
            "origin": Origin.SHOPIFY,
        },
    )


def criar_variantes(produto, dados, decimal):
    recebidas = (dados.get("variants") or {}).get("nodes") or [{}]
    for posicao, recebida in enumerate(recebidas):
        campos = _campos(recebida, decimal, posicao)
        if len(recebidas) == 1:
            variante = obter_variante_padrao(produto, **campos)
        else:
            variante = VarianteProduto.objects.create(produto=produto, **campos)
        _referenciar_variante(variante, recebida.get("id"), dados["id"])
        sincronizar_opcoes(variante, recebida.get("selectedOptions"))


def _por_referencia(produto, externo_id):
    referencia = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY,
        entity_type="variantes",
        external_id=externo_id,
    ).first()
    if not referencia:
        return None
    return produto.variantes.filter(pk=referencia.object_id).first()


def atualizar_variantes(produto, dados, decimal, sobrescrever=False):
    produto_externo_id = dados["id"]
    recebidas = (dados.get("variants") or {}).get("nodes") or []
    for recebida in recebidas:
        variante = _por_referencia(produto, recebida.get("id"))
        if variante is None and recebida.get("sku"):
            variante = produto.variantes.filter(sku=recebida["sku"]).first()
        if variante is None and len(recebidas) == 1:
            variante = produto.variante_padrao
        if variante is None:
            continue
        regular, promocional, comparacao = _precos(recebida, decimal)
        variante.price = regular
        variante.sale_price = promocional
        variante.compare_at_price = comparacao
        if sobrescrever:
            _titulo_e_sku(variante, recebida, produto_externo_id)
        if recebida.get("inventoryQuantity") is not None:
            variante.inventory_quantity = recebida["inventoryQuantity"]
        for campo, valor in _sem_barcode_repetido(
                variante, _logistica(recebida), produto_externo_id).items():
            setattr(variante, campo, valor)
        variante.save()
        _referenciar_variante(variante, recebida.get("id"), dados["id"])


def _titulo_e_sku(variante, recebida, produto_externo_id=""):
    """Importacao: titulo, posicao e SKU da loja; SKU de outra variante do hub nao entra."""
    if recebida.get("title"):
        variante.titulo = recebida["title"]
    if recebida.get("position"):
        variante.posicao = max(int(recebida["position"]) - 1, 0)
    sku = recebida.get("sku") or ""
    if sku and sku != variante.sku:
        if VarianteProduto.objects.filter(sku=sku).exclude(pk=variante.pk).exists():
            avisar(f"SKU {sku} da loja ja e de outra variante no hub; "
                   f"o da variante {variante.sku or variante.pk} nao foi trocado.",
                   recurso="produtos", id=variante.produto_id,
                   descricao=variante.produto.nome, id_externo=produto_externo_id)
        else:
            variante.sku = sku


def _sem_barcode_repetido(variante, campos, externo_id=""):
    """Tira o barcode que outra variante da conta ja usa (indice unico por conta).

    Gravar quebraria a importacao do produto inteiro por um codigo duplicado na loja;
    a variante fica com o barcode antigo e o aviso vai para a mensagem da execucao.
    """
    barcode = campos.get("barcode")
    if barcode and VarianteProduto.objects.filter(barcode=barcode).exclude(
        pk=variante.pk
    ).exists():
        campos.pop("barcode")
        avisar(f"Codigo de barras {barcode} da variante {variante.sku or variante.pk} "
               "ja e de outra variante no hub; corrija na loja ou no hub.",
               recurso="produtos", id=variante.produto_id, descricao=variante.produto.nome,
               id_externo=externo_id)
    return campos
