import re

from apps.starchats.contexto import para_texto, resolver

VARIAVEL = re.compile(r"{{\s*([^{}]+?)\s*}}")


def parametros(conjunto, contexto):
    return mapear(conjunto.parametros_corpo, contexto)


def mapear(mapeamento, contexto):
    return {
        str(chave): para_texto(resolver(contexto, caminho))
        for chave, caminho in (mapeamento or {}).items()
    }


def renderizar(conteudo, valores):
    return VARIAVEL.sub(lambda item: valores.get(item.group(1), item.group(0)), conteudo or "")


def preparar(conjunto, contexto):
    valores = parametros(conjunto, contexto)
    return renderizar(conjunto.modelo.conteudo, valores), valores
