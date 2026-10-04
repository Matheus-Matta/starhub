"""Tarefas do Celery da logistica: importar faixas de CEP por planilha.

O motor (arquivo no MEDIA, barra, falhas por linha, Retomar) e o de toda importacao:
apps/integracoes/importar_planilha.py. Aqui so a regra da linha e o "substituir".
"""

from celery import shared_task

from apps.integracoes import importar_planilha
from apps.logistica.importacao import importar_faixa
from apps.logistica.models import FaixaCep, TabelaFrete


def _quem(dados):
    """"Grande SP · 01000-000 a 05999-999": como o operador acha a linha na planilha."""
    return (f"{dados.get('tabela') or 'sem tabela'} · {dados.get('cep_inicial') or '-'} a "
            f"{dados.get('cep_final') or '-'}")


def _substituir(execucao, linhas):
    """Opcao "substituir": a planilha e a tabela inteira; as faixas antigas saem antes."""
    if not (execucao.parametros or {}).get("substituir"):
        return
    nomes = {(dados.get("tabela") or "").strip().lower() for _, dados in linhas}
    tabelas = [t.pk for t in TabelaFrete.objects.filter(tipo=TabelaFrete.Tipo.FAIXA_CEP)
               if t.nome.lower() in nomes]
    FaixaCep.objects.filter(tabela_id__in=tabelas).delete()


@shared_task
def importar_faixas(execucao_id):
    return importar_planilha.executar(execucao_id, importar_faixa, objeto="faixas",
                                      recurso="frete", quem=_quem, preparar=_substituir)
