"""Opcoes (Cor, Tamanho) das variantes do Shopify no catalogo do hub."""

from apps.core.models import Origin
from apps.loja.models import TipoVariante, ValorDaVarianteProduto, ValorVariante


def _tipo(nome, posicao):
    existente = TipoVariante.objects.filter(nome__iexact=nome).first()
    return existente or TipoVariante.objects.create(
        nome=nome, posicao=posicao, origin=Origin.SHOPIFY
    )


def _valor(tipo, texto, posicao):
    existente = ValorVariante.objects.filter(
        tipo=tipo, valor_normalizado=texto.casefold()
    ).first()
    return existente or ValorVariante.objects.create(
        tipo=tipo, valor=texto, posicao=posicao, origin=Origin.SHOPIFY
    )


def sincronizar_opcoes(variante, opcoes):
    for posicao, opcao in enumerate(opcoes or []):
        nome, texto = opcao.get("name"), str(opcao.get("value") or "").strip()
        if not nome or not texto:
            continue
        tipo = _tipo(nome, posicao)
        valor = _valor(tipo, texto, posicao)
        ValorDaVarianteProduto.objects.get_or_create(
            variante=variante,
            valor=valor,
            defaults={"origin": Origin.SHOPIFY},
        )
