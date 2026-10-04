"""Cotacao de frete de uma tabela para um CEP de destino.

    cotar(tabela, "20040-020") -> Cotacao(valor=Decimal("129.90"), prazo_dias=3, ...)

Por distancia: taxa fixa + km x preco por km (arredondado ao centavo), nunca abaixo do
valor minimo; acima da distancia maxima, FreteIndisponivel. Por faixa de CEP: a faixa
que contem o CEP; se mais de uma contiver, vale a mais estreita (a mais especifica).
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from apps.logistica import geo
from apps.logistica.models import TabelaFrete
from apps.loja.dinheiro import dinheiro


class FreteIndisponivel(Exception):
    """Nao ha frete para o CEP: a mensagem diz por que (vai para quem cotou)."""


@dataclass(frozen=True)
class Cotacao:
    valor: Decimal
    prazo_dias: int
    distancia_km: Decimal | None = None
    detalhe: str = ""


def normalizar_cep(cep):
    digitos = re.sub(r"\D", "", str(cep or ""))
    if len(digitos) != 8:
        raise FreteIndisponivel(f"CEP '{cep}' invalido: informe os 8 digitos.")
    return digitos


def _por_faixa(tabela, cep):
    faixas = [f for f in tabela.faixas.all() if f.cep_inicial <= cep <= f.cep_final]
    if not faixas:
        raise FreteIndisponivel(f"O CEP {cep} nao esta em nenhuma faixa de '{tabela.nome}'.")
    faixa = min(faixas, key=lambda f: (int(f.cep_final) - int(f.cep_inicial), f.cep_inicial))
    prazo = faixa.prazo_dias if faixa.prazo_dias is not None else tabela.prazo_dias
    return Cotacao(valor=dinheiro(faixa.valor), prazo_dias=prazo,
                   detalhe=f"Faixa {faixa.cep_inicial} a {faixa.cep_final}")


def _por_distancia(tabela, cep, timeout, cidade, uf):
    try:
        km, exata = geo.km_entre_ceps(tabela.cep_origem, cep, timeout, cidade, uf)
    except geo.GeoErro as erro:
        raise FreteIndisponivel(str(erro)) from erro
    if tabela.distancia_maxima_km is not None and km > tabela.distancia_maxima_km:
        raise FreteIndisponivel(
            f"{km} km passa da distancia maxima de {tabela.distancia_maxima_km} km.")
    por_km = dinheiro(km * tabela.preco_por_km)
    valor = max(dinheiro(tabela.taxa_fixa) + por_km, dinheiro(tabela.valor_minimo))
    detalhe = (f"{km} km por estrada" if exata
               else f"{km} km estimados (linha reta x {geo.FATOR_ESTRADA}; rota indisponivel)")
    return Cotacao(valor=valor, prazo_dias=tabela.prazo_dias, distancia_km=km, detalhe=detalhe)


def cotar(tabela, cep_destino, timeout=geo.TIMEOUT, cidade="", uf=""):
    """Cotacao da tabela para o CEP; `timeout` limita cada API externa (checkout: curto).

    `cidade`/`uf` sao a reserva para localizar CEP que as bases nao conhecem.
    """
    if not tabela.active:
        raise FreteIndisponivel(f"A tabela '{tabela.nome}' esta desativada.")
    cep = normalizar_cep(cep_destino)
    if tabela.tipo == TabelaFrete.Tipo.FAIXA_CEP:
        return _por_faixa(tabela, cep)
    return _por_distancia(tabela, cep, timeout, cidade, uf)
