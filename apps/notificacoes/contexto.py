"""Sino do cabecalho: quantas nao lidas e as ultimas, em toda pagina do admin."""

from apps.notificacoes.entrega import para_tela

ULTIMAS = 8


def notificacoes(request):
    usuario = getattr(request, "user", None)
    if not (usuario and usuario.is_authenticated and usuario.is_staff):
        return {}
    from apps.notificacoes.models import Notificacao

    # all_objects: o sino e do usuario, que pode ser superusuario olhando outra conta.
    minhas = Notificacao.all_objects.filter(usuario=usuario)
    return {"notificacoes_nao_lidas": minhas.filter(lida=False).count(),
            "notificacoes_ultimas": [para_tela(n) for n in minhas[:ULTIMAS]]}
