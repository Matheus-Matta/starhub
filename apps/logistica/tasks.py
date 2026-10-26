"""Tarefas do Celery da logistica: importar faixas de CEP e refinar o motor de CEP.

O motor (arquivo no MEDIA, barra, falhas por linha, Retomar) e o de toda importacao:
apps/integracoes/importar_planilha.py. Aqui so a regra da linha e o "substituir".
"""

from celery import shared_task

from apps.core.tenant.context import tenant_context
from apps.integracoes import importar_planilha
from apps.integracoes.models import ExecucaoIntegracao
from apps.logistica.importacao import importar_faixa
from apps.logistica.models import FaixaCep, TabelaFrete
from apps.logistica.sinais import tabelas_alteradas


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
    resultado = importar_planilha.executar(execucao_id, importar_faixa, objeto="faixas",
                                           recurso="frete", quem=_quem, preparar=_substituir)
    conta = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).values_list(
        "account_id", flat=True).first()
    with tenant_context(conta):
        tabelas_alteradas.send(sender=TabelaFrete)
    return resultado


@shared_task(ignore_result=True)
def refinar_cep(cep):
    """CEP guardado como aproximado: procura o ponto dele com calma, sem o limite do
    checkout. Achou, troca e apaga as distancias dele (a proxima cotacao recalcula)."""
    from apps.logistica import geo
    from apps.logistica.models import CoordenadaCep, DistanciaCep

    try:
        ponto = geo.localizar(cep, so_exato=True)
    except geo.GeoErro:
        ponto = None
    if ponto is None:
        return  # fica o aproximado; a proxima cotacao que o usar agenda de novo
    CoordenadaCep.objects.filter(cep=cep).update(
        latitude=ponto.latitude, longitude=ponto.longitude, fonte=ponto.fonte[:30],
        aproximada=False)
    DistanciaCep.objects.filter(destino=cep).delete()


@shared_task(ignore_result=True)
def refinar_distancia(origem_cep, destino_cep):
    """Distancia guardada como estimativa: tenta a rota de carro de novo."""
    from apps.logistica import geo
    from apps.logistica.models import DistanciaCep

    km, exata = geo.distancia_km(geo.coordenada(origem_cep), geo.coordenada(destino_cep))
    if exata:
        DistanciaCep.objects.filter(origem=origem_cep, destino=destino_cep).update(
            km=km, exata=True)
