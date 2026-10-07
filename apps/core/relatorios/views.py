"""Pagina do relatorio (/admin/relatorios/<chave>/): periodo, previa e download.

    ?de=2026-09-01&ate=2026-09-30            previa na tela
    ?de=...&ate=...&formato=xlsx | pdf       arquivo
Sem `de` nem `ate` na URL, abre no mes atual (o "tudo" pesaria em loja grande).
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.core.filtros import ler_data
from apps.core.relatorios import exportar, registro

PREVIA = 50  # linhas na tela; o arquivo leva o periodo inteiro


def _periodo(request):
    if "de" not in request.GET and "ate" not in request.GET:
        hoje = timezone.localdate()
        return hoje.replace(day=1), hoje
    return ler_data(request.GET.get("de")), ler_data(request.GET.get("ate"))


def _query(de, ate, **extra):
    partes = {"de": de.isoformat() if de else "", "ate": ate.isoformat() if ate else "", **extra}
    return "?" + "&".join(f"{nome}={valor}" for nome, valor in partes.items())


def _para_tela(tabela):
    reais = tabela.moeda
    return {
        "titulo": tabela.titulo,
        "colunas": [(coluna, indice in reais) for indice, coluna in enumerate(tabela.colunas)],
        "linhas": [[(exportar.texto(valor, indice in reais), indice in reais)
                    for indice, valor in enumerate(linha)] for linha in tabela.linhas],
    }


def _exportar(request, relatorio, formato, de, ate):
    limite = exportar.LIMITES[formato]
    resultado = relatorio.gerar(request, de, ate, limite)
    if resultado.total > limite:
        messages.error(request, (
            f"O periodo tem {resultado.total} registros e o {formato.upper()} aceita ate "
            f"{limite}. Escolha um periodo menor ou use o Excel."
            if formato == "pdf" else
            f"O periodo tem {resultado.total} registros e o Excel aceita ate {limite}. "
            "Escolha um periodo menor."
        ))
        return redirect(request.path + _query(de, ate))
    return exportar.resposta(relatorio, resultado, formato, de, ate)


def relatorio_view(admin_site, request, chave):
    relatorio = registro.buscar(chave)
    if relatorio is None:
        raise Http404("Relatorio nao encontrado.")
    if not relatorio.permitido(request):
        raise PermissionDenied
    de, ate = _periodo(request)
    formato = request.GET.get("formato")
    if formato in exportar.TIPOS:
        return _exportar(request, relatorio, formato, de, ate)
    resultado = relatorio.gerar(request, de, ate, PREVIA, painel=True)
    contexto = {
        **admin_site.each_context(request),
        "title": relatorio.titulo,
        "subtitle": None,
        "relatorio": relatorio,
        "total": resultado.total,
        "indicadores": resultado.indicadores,
        "graficos": resultado.graficos,
        "aviso_previa": (
            f"Mostrando {len(resultado.principal.linhas)} de {resultado.total}; "
            "o Excel e o PDF levam o periodo inteiro."
            if resultado.total > len(resultado.principal.linhas) else None),
        "principal": _para_tela(resultado.principal),
        "resumos": [_para_tela(resumo) for resumo in resultado.resumos],
        "de": de.isoformat() if de else "",
        "ate": ate.isoformat() if ate else "",
        "periodo": exportar.descrever_periodo(de, ate),
        "url_xlsx": request.path + _query(de, ate, formato="xlsx"),
        "url_pdf": request.path + _query(de, ate, formato="pdf"),
    }
    return TemplateResponse(request, "admin/relatorio.html", contexto)
