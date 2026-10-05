"""Zonas de entrega do Woo a partir das tabelas de frete do hub (por faixa de CEP).

    zonas, avisos = zonas_desejadas()
    # [{"inicio": "01000000", "fim": "01099999",
    #   "metodos": [{"tabela": 3, "titulo": "Expressa (2 dias uteis)", "custo": "19.90"}]}]

O Woo usa os metodos de UMA zona por CEP (a primeira que casa). Uma zona por faixa
esconderia as tabelas de faixas sobrepostas. Por isso o CEP e cortado em segmentos
pelos limites de todas as faixas: dentro de um segmento nenhuma faixa comeca nem
termina, entao `cotar` (a mesma regra do hub: vale a faixa mais estreita) da o mesmo
preco para qualquer CEP dele. Segmentos vizinhos com os mesmos metodos viram uma zona.
"""

from apps.logistica.cotacao import FreteIndisponivel, cotar
from apps.logistica.models import TabelaFrete
from apps.loja.dinheiro import texto


def _tabelas():
    return list(TabelaFrete.objects.filter(active=True, no_checkout=True)
                .prefetch_related("faixas").order_by("nome", "pk"))


def _titulo(tabela, cotacao):
    if cotacao.prazo_dias:
        return f"{tabela.nome} ({cotacao.prazo_dias} dias uteis)"
    return tabela.nome


def _metodos(tabelas, cep):
    metodos = []
    for tabela in tabelas:
        try:
            cotacao = cotar(tabela, cep)
        except FreteIndisponivel:
            continue
        metodos.append({"tabela": tabela.pk, "titulo": _titulo(tabela, cotacao),
                        "custo": texto(cotacao.valor)})
    return metodos


def _limites(tabelas):
    pontos = set()
    for tabela in tabelas:
        for faixa in tabela.faixas.all():
            pontos.update((int(faixa.cep_inicial), int(faixa.cep_final) + 1))
    return sorted(pontos)


def zonas_desejadas():
    """(zonas, avisos): tabela por distancia nao vira zona (o Woo so casa CEP)."""
    todas = _tabelas()
    avisos = [f"Tabela '{t.nome}' e por distancia: o Woo so aceita faixa de CEP e ela "
              "ficou fora do checkout da loja." for t in todas
              if t.tipo == TabelaFrete.Tipo.DISTANCIA]
    tabelas = [t for t in todas if t.tipo == TabelaFrete.Tipo.FAIXA_CEP]
    limites = _limites(tabelas)
    zonas = []
    for inicio, proximo in zip(limites, limites[1:], strict=False):
        metodos = _metodos(tabelas, f"{inicio:08d}")
        if not metodos:
            continue
        anterior = zonas[-1] if zonas else None
        if anterior and int(anterior["fim"]) + 1 == inicio and anterior["metodos"] == metodos:
            anterior["fim"] = f"{proximo - 1:08d}"
        else:
            zonas.append({"inicio": f"{inicio:08d}", "fim": f"{proximo - 1:08d}",
                          "metodos": metodos})
    return zonas, avisos
