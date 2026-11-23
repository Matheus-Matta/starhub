"""Gera Excel e PDF da listagem filtrada dentro do worker."""

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.relatorios import exportar, pdf
from apps.core.relatorios.modelos import RelatorioModelo
from apps.core.tenant.context import bind_tenant, reset_tenant
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.tarefa_estado import _gravar

ABERTAS = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)


def _request(execucao, usuario, model_admin):
    parametros = execucao.parametros or {}
    info = model_admin.opts.app_label, model_admin.opts.model_name
    caminho = reverse(f"admin:{info[0]}_{info[1]}_changelist")
    query = parametros.get("query", "")
    request = RequestFactory().get(f"{caminho}?{query}" if query else caminho)
    request.user = usuario
    request.tenant_account_id = usuario.account_id
    request.tenant_todas_as_contas = bool(usuario.is_superuser)
    return request


def _preparar(execucao):
    parametros = execucao.parametros or {}
    modelo = apps.get_model(parametros.get("modelo", ""))
    model_admin = admin.site._registry.get(modelo)
    usuario = get_user_model().objects.filter(pk=parametros.get("usuario_id")).first()
    if model_admin is None or usuario is None or not usuario.is_active or not usuario.is_staff:
        raise PermissionDenied("Usuario ou cadastro nao esta mais disponivel para exportacao.")
    if not usuario.is_superuser and usuario.account_id != execucao.account_id:
        raise PermissionDenied("A tarefa e o usuario pertencem a contas diferentes.")
    request = _request(execucao, usuario, model_admin)
    return usuario, request, model_admin


def _passo(execucao, percentual, etapa, **campos):
    _gravar(execucao, progresso=percentual, etapa=etapa, **campos)


def _salvar(execucao, relatorio, resultado):
    instante = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    base = f"{relatorio.nome_arquivo or 'relatorio'}-{instante}"
    pasta = f"relatorios/{execucao.account_id}/{execucao.uuid}"
    descricao = (
        "Filtros aplicados na listagem"
        if (execucao.parametros or {}).get("query") else "Todos os registros da listagem"
    )
    conteudos = {
        "xlsx": exportar.xlsx(resultado),
        "pdf": pdf.gerar(relatorio.titulo, descricao, resultado, exportar.texto),
    }
    arquivos, salvos = {}, []
    try:
        for formato, conteudo in conteudos.items():
            nome = f"{slugify(base) or 'relatorio'}.{formato}"
            caminho = default_storage.save(f"{pasta}/{nome}", ContentFile(conteudo))
            salvos.append(caminho)
            arquivos[formato] = {"caminho": caminho, "nome": nome}
        return arquivos
    except Exception:
        for caminho in salvos:
            default_storage.delete(caminho)
        raise


def executar(execucao_id):
    execucao = ExecucaoIntegracao.all_objects.get(pk=execucao_id)
    comecou = ExecucaoIntegracao.all_objects.filter(
        pk=execucao.pk, status__in=ABERTAS
    ).update(
        status=ExecucaoIntegracao.Status.PROCESSANDO, etapa="Preparando filtros",
        iniciada_em=timezone.now(), updated_at=timezone.now(),
    )
    if not comecou:
        return {"status": "ignored", "message": "tarefa ja encerrada"}
    arquivos = []
    tokens = None
    try:
        usuario, request, model_admin = _preparar(execucao)
        tokens = bind_tenant(
            execucao.account_id, usuario, todas_as_contas=bool(usuario.is_superuser)
        )
        if not model_admin.has_view_or_change_permission(request):
            raise PermissionDenied("O usuario nao possui mais permissao para este cadastro.")
        consulta = model_admin.get_changelist_instance(request).queryset
        total = consulta.count()
        _passo(execucao, 10, "Lendo registros filtrados", total=total)
        relatorio = RelatorioModelo(model_admin.model, model_admin)
        resultado = relatorio.gerar_consulta(request, consulta)
        _passo(execucao, 65, "Gerando Excel", processados=total)
        gerados = _salvar(execucao, relatorio, resultado)
        arquivos = [item["caminho"] for item in gerados.values()]
        parametros = {**(execucao.parametros or {}), "arquivos": gerados}
        _gravar(
            execucao, status=ExecucaoIntegracao.Status.CONCLUIDA, progresso=100,
            processados=total, total=total, etapa="Concluida",
            mensagem=f"{total} registro(s) exportado(s) em Excel e PDF.",
            parametros=parametros, concluida_em=timezone.now(),
        )
        return {"status": "completed", "total": total}
    except Exception as erro:
        for caminho in arquivos:
            default_storage.delete(caminho)
        _gravar(
            execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
            mensagem=str(erro)[:4000], concluida_em=timezone.now(),
        )
        return {"status": "failed", "message": str(erro)}
    finally:
        if tokens:
            reset_tenant(tokens)
