"""Downloads privados produzidos por uma tarefa de exportacao."""

from pathlib import PurePath

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.urls import reverse

from apps.integracoes.models import ExecucaoIntegracao

TIPOS = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _item(execucao, formato):
    if (
        execucao.tipo != ExecucaoIntegracao.Tipo.EXPORTAR_RELATORIO
        or execucao.status != ExecucaoIntegracao.Status.CONCLUIDA
        or formato not in TIPOS
    ):
        return None
    item = (execucao.parametros or {}).get("arquivos", {}).get(formato)
    return item if isinstance(item, dict) and item.get("caminho") else None


def _permitido(request, execucao):
    try:
        modelo = apps.get_model((execucao.parametros or {}).get("modelo", ""))
    except (LookupError, ValueError):
        return False
    model_admin = admin.site._registry.get(modelo)
    return bool(model_admin and model_admin.has_view_or_change_permission(request))


def para_tela(request, execucao):
    if not _permitido(request, execucao):
        return []
    rotulos = {"xlsx": "Baixar Excel", "pdf": "Baixar PDF"}
    icones = {"xlsx": "file-spreadsheet", "pdf": "file-text"}
    return [
        {
            "formato": formato,
            "rotulo": rotulos[formato],
            "icone": icones[formato],
            "url": reverse(
                "admin:integracoes_execucaointegracao_arquivo",
                args=[execucao.pk, formato],
            ),
        }
        for formato in TIPOS
        if _item(execucao, formato)
    ]


def resposta(request, execucao, formato):
    if not _permitido(request, execucao):
        raise PermissionDenied
    item = _item(execucao, formato)
    if item is None or not default_storage.exists(item["caminho"]):
        raise Http404("Arquivo da exportacao nao encontrado.")
    nome = PurePath(item.get("nome") or f"relatorio.{formato}").name
    return FileResponse(
        default_storage.open(item["caminho"], "rb"),
        as_attachment=True,
        filename=nome,
        content_type=TIPOS[formato],
    )
