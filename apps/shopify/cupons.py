"""Cupom vindo do Shopify: acha ou cadastra a partir do desconto completo.

    cupom = garantir_cupom("PROMO10", padrao)   # cupom usado num pedido
    cupom, criado = importar_desconto(node)      # sincronizacao e webhook create
    cupom = atualizar_desconto(cupom, node)      # webhook update

O cupom e identificado pelo nome na conta (indice unico); o codigo que o cliente
digita fica numa ExternalReference "cupons_codigos", para o segundo pedido com o
mesmo codigo nao consultar o Shopify de novo. Erro de rede/API sobe de proposito,
como em pedidos_produtos.garantir_produto: o pedido desfaz e pode ser reprocessado.
"""

import logging

from django.db import IntegrityError, transaction

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Cupom
from apps.shopify.cliente import ShopifyClient
from apps.shopify.consultas_cupons import CONSULTA_CUPOM_POR_CODIGO, CONSULTA_CUPOM_POR_ID
from apps.shopify.contexto import configuracao_atual
from apps.shopify.cupons_mapa import aplicar_listas, codigos, mapear
from apps.shopify.cupons_vinculo import ENTIDADE, gravar, vinculo

logger = logging.getLogger(__name__)
CODIGOS = "cupons_codigos"


def _referencia(entidade, externo_id):
    referencia = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id=externo_id).first()
    return Cupom.objects.filter(pk=referencia.object_id).first() if referencia else None


def _referenciar_codigos(node, cupom):
    # O Shopify trata o codigo sem diferenciar maiusculas; a chave vai em maiusculas.
    for codigo in codigos(node):
        ExternalReference.objects.update_or_create(
            platform=Origin.SHOPIFY, entity_type=CODIGOS, external_id=codigo.upper(),
            defaults={"object_id": str(cupom.pk), "origin": Origin.SHOPIFY})


def _registrar_faltantes(extras, faltando):
    if faltando:
        extras["nao_encontrados"] = faltando


def _pelo_nome(nome, defaults):
    """Nome igual sem diferenciar maiusculas reaproveita; o get_or_create no indice
    unico (conta, nome) segura dois pedidos criando o mesmo cupom ao mesmo tempo."""
    existente = Cupom.objects.filter(name__iexact=nome).order_by("pk").first()
    if existente:
        return existente, False
    return Cupom.objects.get_or_create(name=nome, defaults=defaults)


def importar_desconto(node, padrao=None):
    """Cupom do desconto; `padrao` (tipo/valor do pedido) cobre o que o no nao tem."""
    cupom, criado = _referencia(ENTIDADE, node["id"]), False
    if cupom is None:
        campos, listas, extras = mapear(node)
        nome = campos.pop("name") or next(iter(codigos(node)), "") or node["id"]
        defaults = {"discount_type": Cupom.TipoDesconto.VALOR_FIXO, **(padrao or {}),
                    **campos, "origin": Origin.SHOPIFY}
        cupom, criado = _pelo_nome(nome, defaults)
        referencia, _ = ExternalReference.objects.get_or_create(
            platform=Origin.SHOPIFY, entity_type=ENTIDADE, external_id=node["id"],
            defaults={"object_id": str(cupom.pk), "origin": Origin.SHOPIFY})
        if criado and listas is not None:
            _registrar_faltantes(extras, aplicar_listas(cupom, listas))
        gravar(referencia, extras, substituir=True)
    _referenciar_codigos(node, cupom)
    return cupom, criado


def atualizar_desconto(cupom, node):
    """O Shopify manda no cupom vinculado: reaplica tudo que o no traz."""
    campos, listas, extras = mapear(node)
    nome = campos.pop("name")
    for campo, valor in campos.items():
        setattr(cupom, campo, valor)
    cupom.name = nome or cupom.name
    try:
        with transaction.atomic():
            cupom.save()
    except IntegrityError as erro:
        raise ValueError(
            f'Ja existe outro cupom chamado "{nome}" no hub. Renomeie um dos dois '
            "(no hub ou no Shopify) e reprocesse o webhook.") from erro
    if listas is not None:
        _registrar_faltantes(extras, aplicar_listas(cupom, listas))
    # Corpo magro (sem regras) mescla: substituir apagaria tipo e frete maximo.
    gravar(vinculo(cupom), extras, substituir=listas is not None)
    _referenciar_codigos(node, cupom)
    return cupom


def buscar_desconto(desconto_gid):
    """No completo do desconto, ou None sem loja no contexto ou se ele sumiu."""
    configuracao = configuracao_atual()
    if configuracao is None:
        return None
    dados = ShopifyClient(configuracao).graphql(CONSULTA_CUPOM_POR_ID, {"id": desconto_gid})
    return dados.get("codeDiscountNode")


def garantir_cupom(codigo, padrao):
    """Cupom do codigo usado no pedido. `padrao` e o que o pedido informa (tipo,
    valor, frete gratis) e so vale quando o Shopify nao detalha o desconto."""
    cupom = _referencia(CODIGOS, codigo.upper())
    if cupom:
        return cupom
    configuracao, node = configuracao_atual(), None
    if configuracao is None:
        logger.warning("Sem loja Shopify no contexto para consultar o cupom %s; "
                       "cadastro pelo que o pedido informa.", codigo)
    else:
        node = ShopifyClient(configuracao).graphql(
            CONSULTA_CUPOM_POR_CODIGO, {"code": codigo}).get("codeDiscountNodeByCode")
        if not node:
            logger.warning("Cupom %s nao existe no Shopify; cadastro pelo que o pedido "
                           "informa.", codigo)
    if node:
        return importar_desconto(node, padrao)[0]
    cupom, _criado = _pelo_nome(codigo, {**padrao, "status": Cupom.Status.ATIVO,
                                         "origin": Origin.SHOPIFY})
    return cupom
