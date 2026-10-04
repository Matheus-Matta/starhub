"""Tela "Sincronizar loja": POST do modal em etapas e resumo legivel da tarefa."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.integracoes import sincronizacao
from apps.integracoes.permissoes import RECURSOS

ROTULOS_DIRECAO = {sincronizacao.IMPORTAR: "Importar", sincronizacao.EXPORTAR: "Exportar"}


def url_execucao(execucao):
    return reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk])


def listas_do_modal(configuracao):
    """As duas listas de uma vez: o JS do modal mostra a da direcao escolhida."""
    if configuracao is None or not configuracao.pk:
        return None
    return {
        direcao: sincronizacao.recursos_disponiveis(configuracao, direcao)
        for direcao in (sincronizacao.IMPORTAR, sincronizacao.EXPORTAR)
    }


def processar_sincronizacao(request, configuracao, pagina):
    """POST do modal. Sempre devolve um redirect: tarefa criada ou de volta a tela."""
    if configuracao is None or not configuracao.pk:
        messages.error(request, "Salve a configuracao da Shopify antes de sincronizar.")
        return HttpResponseRedirect(pagina)
    try:
        execucao = sincronizacao.iniciar(
            configuracao, request.POST.get("direcao", ""), request.POST.getlist("recursos")
        )
    except sincronizacao.SincronizacaoEmAndamento as andamento:
        messages.warning(request, format_html(
            'Ja existe uma sincronizacao em andamento. <a href="{}">Acompanhe a tarefa</a> '
            "e crie outra quando ela terminar.", url_execucao(andamento.execucao),
        ))
        return HttpResponseRedirect(pagina)
    except ValueError as erro:
        messages.error(request, str(erro))
        return HttpResponseRedirect(pagina)
    messages.success(request, f"{execucao.get_tipo_display()} foi enviada para a fila.")
    return HttpResponseRedirect(url_execucao(execucao))


def parametros_legiveis(execucao):
    """Direcao e dados pedidos em texto: campo JSON nunca aparece cru (AGENTS.md)."""
    parametros = execucao.parametros or {}
    # Envio e webhook guardam so "reenvio" (dados para o Retomar): nao e um pedido de tela.
    if not parametros.get("direcao"):
        return "-"
    rotulos = dict(RECURSOS)
    direcao = ROTULOS_DIRECAO.get(parametros.get("direcao"), parametros.get("direcao") or "-")
    itens = format_html_join(
        "", "<li>{}</li>", ((rotulos.get(r, r),) for r in parametros.get("recursos", []))
    )
    return format_html("<strong>{}</strong><ul>{}</ul>", direcao, itens)


def falhas_legiveis(execucao):
    """Tabela das falhas por item: campo JSON nunca aparece cru (AGENTS.md)."""
    if not execucao.falhas:
        return "-"
    rotulos = dict(RECURSOS)
    falhas = [
        # Recurso fora da matriz (ex.: "frete" da importacao) aparece com maiuscula.
        {**falha, "rotulo": rotulos.get(falha.get("recurso"),
                                        str(falha.get("recurso", "")).capitalize())}
        for falha in execucao.falhas if isinstance(falha, dict)
    ]
    return render_to_string("components/tabela_falhas.html", {"falhas": falhas})
