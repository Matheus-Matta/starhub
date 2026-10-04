"""Tarefas do Celery da loja: importar a planilha de avaliacoes.

O motor (arquivo no MEDIA, barra, falhas por linha, Retomar) e o mesmo de toda
importacao: apps/integracoes/importar_planilha.py. Aqui so a regra da linha.
"""

from celery import shared_task

from apps.integracoes import importar_planilha
from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.services.avaliacoes_importacao import importar_linha


def _quem(dados):
    """"ana@x.com · SKU POL-001": como o operador acha a linha na planilha."""
    email = dados.get("email") or dados.get("e_mail") or "sem e-mail"
    return f"{email} · SKU {dados.get('sku') or '-'}"


@shared_task
def importar_avaliacoes(execucao_id):
    usuario = ExecucaoIntegracao.all_objects.select_related("created_by").get(
        pk=execucao_id).created_by
    return importar_planilha.executar(
        execucao_id, lambda dados: importar_linha(dados, usuario),
        objeto="avaliacoes", recurso="avaliacoes", quem=_quem)
