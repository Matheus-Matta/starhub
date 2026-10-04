"""Uma linha da planilha de frete -> faixa de CEP numa tabela (apps/logistica/tasks.py).

Colunas: tabela (nome), cep_inicial, cep_final, valor e, opcional, prazo_dias.

- Tabela que nao existe e criada como "Por faixa de CEP"; com o nome de uma tabela
  por distancia, a linha e recusada (faixa nao vale para ela).
- Mesma tabela + mesmo CEP inicial e final atualiza valor e prazo: importar de novo a
  planilha corrigida nao duplica.
- Faixa que cruza outra da tabela e recusada com o motivo: para o mesmo CEP o cliente
  pagaria um de dois valores.
"""

import re

from django.db import transaction

from apps.integracoes.importar_planilha import LinhaInvalida
from apps.logistica.models import FaixaCep, TabelaFrete
from apps.loja.dinheiro import ValorInvalido, dinheiro

Tipo = TabelaFrete.Tipo


def _cep(dados, coluna):
    digitos = re.sub(r"\D", "", dados.get(coluna, ""))
    if len(digitos) != 8:
        raise LinhaInvalida(f"{coluna} '{dados.get(coluna, '')}' invalido: use 8 digitos.")
    return digitos


def _valor(texto):
    bruto = str(texto or "").strip().replace("R$", "").strip()
    if "," in bruto:  # "1.234,56" e o formato brasileiro do Excel
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        valor = dinheiro(bruto)
    except ValorInvalido as erro:
        raise LinhaInvalida(f"valor '{texto}' invalido; use 19,90.") from erro
    if valor is None or valor < 0:
        raise LinhaInvalida(f"valor '{texto}' invalido; use 19,90.")
    return valor


def _prazo(texto):
    texto = str(texto or "").strip()
    if not texto:
        return None
    if not texto.isdigit():
        raise LinhaInvalida(f"prazo_dias '{texto}' invalido; use um numero de dias.")
    return int(texto)


def _tabela(nome):
    nome = (nome or "").strip()
    if not nome:
        raise LinhaInvalida("falta o nome da tabela.")
    tabela = TabelaFrete.objects.filter(nome__iexact=nome).first()
    if tabela is None:
        return TabelaFrete.objects.create(nome=nome[:150], tipo=Tipo.FAIXA_CEP)
    if tabela.tipo != Tipo.FAIXA_CEP:
        raise LinhaInvalida(f"a tabela '{tabela.nome}' e por distancia; faixa nao vale nela.")
    return tabela


def importar_faixa(dados):
    """(faixa, criada) da linha; LinhaInvalida com o motivo se nao der."""
    inicio, fim = _cep(dados, "cep_inicial"), _cep(dados, "cep_final")
    if inicio > fim:
        raise LinhaInvalida(f"cep_inicial {inicio} maior que o cep_final {fim}.")
    valor, prazo = _valor(dados.get("valor")), _prazo(dados.get("prazo_dias"))
    with transaction.atomic():
        tabela = _tabela(dados.get("tabela"))
        # Lock na tabela: duas importacoes juntas nao podem gravar faixas que se cruzam.
        TabelaFrete.objects.select_for_update().filter(pk=tabela.pk).first()
        faixa = FaixaCep.objects.filter(tabela=tabela, cep_inicial=inicio, cep_final=fim).first()
        cruza = (FaixaCep.objects.filter(tabela=tabela, cep_inicial__lte=fim, cep_final__gte=inicio)
                 .exclude(pk=getattr(faixa, "pk", None)).order_by("cep_inicial").first())
        if cruza is not None:
            raise LinhaInvalida(f"a faixa {inicio}-{fim} cruza com {cruza.cep_inicial}-"
                                f"{cruza.cep_final} da tabela '{tabela.nome}'.")
        criada = faixa is None
        faixa = faixa or FaixaCep(tabela=tabela, cep_inicial=inicio, cep_final=fim)
        faixa.valor, faixa.prazo_dias = valor, prazo
        faixa.save()
    return faixa, criada
