"""Opcoes da variante do Suri ({"Cor": "Azul"}) nos tipos e valores globais do hub."""

from apps.core.models import Origin
from apps.loja.models import TipoVariante, ValorDaVarianteProduto, ValorVariante


def gravar_opcoes(variante, opcoes):
    for posicao, (nome, texto) in enumerate((opcoes or {}).items()):
        texto = str(texto or "").strip()
        if not nome or not texto:
            continue
        tipo = (TipoVariante.objects.filter(nome__iexact=nome).first()
                or TipoVariante.objects.create(nome=nome, posicao=posicao, origin=Origin.SURI))
        valor = (ValorVariante.objects.filter(tipo=tipo, valor_normalizado=texto.casefold())
                 .first() or ValorVariante.objects.create(tipo=tipo, valor=texto,
                                                          posicao=posicao, origin=Origin.SURI))
        ValorDaVarianteProduto.objects.get_or_create(variante=variante, valor=valor,
                                                     defaults={"origin": Origin.SURI})
