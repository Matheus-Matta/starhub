"""Frete do hub no Suri Shop: resposta de orcamento (POST shop/orders/budget).

O Suri nao chama o hub no checkout. O gancho de frete da API e o orcamento: o sistema
de fora manda a logistica (nome, preco, prazo) de um pedido em montagem. Com o frete
ligado, o pedido em montagem (status 0) com CEP e sem entrega escolhida recebe a
cotacao MAIS BARATA das tabelas "oferecer no checkout" (apps/logistica/cotacao.cotar).

O mesmo pedido com o mesmo CEP e os mesmos itens nao e cotado de novo: o ultimo
orcamento fica no vinculo "orcamentos" (metadata com a assinatura do pedido).

Nao verificado contra o Suri real: como o Suri avisa que um pedido espera orcamento e o
`id` do corpo (a doc mostra "cb59936"); aqui vai o id do pedido.
"""

import hashlib
import json

from apps.core.models import ExternalReference, Origin
from apps.logistica.cotacao import FreteIndisponivel, cotar, normalizar_cep
from apps.logistica.models import TabelaFrete
from apps.suri.cliente import SuriClient

CARRINHO, ENTREGA = 0, 1


def frete_ligado(configuracao):
    return ExternalReference.all_objects.filter(
        platform=Origin.SURI, entity_type="frete", object_id=str(configuracao.pk)).exists()


def ligar_frete(configuracao, ligado):
    filtro = {"platform": Origin.SURI, "entity_type": "frete",
              "object_id": str(configuracao.pk)}
    if ligado:
        ExternalReference.objects.get_or_create(**filtro, defaults={
            "external_id": f"frete-{configuracao.pk}", "origin": Origin.SURI})
    else:
        ExternalReference.objects.filter(**filtro).delete()


def _cep(dados):
    endereco = (dados.get("customer") or {}).get("address") or {}
    return endereco.get("zipCode") or "", endereco.get("city") or "", endereco.get("state") or ""


def precisa_orcamento(dados):
    return (dados.get("status") == CARRINHO and not dados.get("logistic")
            and bool(dados.get("items")) and bool(_cep(dados)[0]))


def melhor_cotacao(cep, cidade="", uf=""):
    """(tabela, Cotacao) mais barata entre as tabelas do checkout; None se nenhuma atende."""
    opcoes = []
    for tabela in TabelaFrete.objects.filter(active=True, no_checkout=True).prefetch_related(
            "faixas"):
        try:
            opcoes.append((tabela, cotar(tabela, cep, cidade=cidade, uf=uf)))
        except FreteIndisponivel:
            continue
    return min(opcoes, key=lambda o: (o[1].valor, o[1].prazo_dias), default=None)


def _assinatura(cep, itens):
    chave = json.dumps([cep, [(i.get("sku"), str(i.get("quantity"))) for i in itens]])
    return hashlib.sha256(chave.encode()).hexdigest()[:16]


def corpo_orcamento(dados, tabela, cotacao):
    prazo = f"{cotacao.prazo_dias} dias uteis" if cotacao.prazo_dias else "a combinar"
    return {"id": str(dados["id"]),
            "logistic": {"providerId": f"HUB_{tabela.pk}", "name": tabela.nome,
                         "description": cotacao.detalhe or tabela.nome, "type": ENTREGA,
                         "price": cotacao.valor, "shippingTimeEstimative": prazo},
            "items": [{"fromSellerId": (item.get("logistic") or {}).get("fromSellerId"),
                       "ProductId": item.get("providerId"), "Sku": item.get("sku"),
                       "Name": item.get("name"), "quantity": item.get("quantity"),
                       "unitPrice": item.get("unitPrice"),
                       "discountAmount": item.get("discountAmout") or 0}
                      for item in dados.get("items") or []],
            "errorMessages": []}


def responder_orcamento(configuracao, dados):
    """Manda o frete do pedido em montagem; devolve a mensagem da tarefa."""
    cep, cidade, uf = _cep(dados)
    try:
        cep = normalizar_cep(cep)
    except FreteIndisponivel as erro:
        return f"Orcamento nao enviado: {erro}"
    assinatura = _assinatura(cep, dados.get("items") or [])
    anterior = ExternalReference.objects.filter(
        platform=Origin.SURI, entity_type="orcamentos", external_id=str(dados["id"])).first()
    if anterior and (anterior.metadata or {}).get("assinatura") == assinatura:
        return "Orcamento ja enviado para este CEP e estes itens."
    achado = melhor_cotacao(cep, cidade, uf)
    if achado is None:
        corpo = {"id": str(dados["id"]), "items": [], "errorMessages": [
            f"Nao entregamos no CEP {cep}."]}
    else:
        corpo = corpo_orcamento(dados, *achado)
    SuriClient(configuracao).post("shop/orders/budget", corpo)
    ExternalReference.objects.update_or_create(
        platform=Origin.SURI, entity_type="orcamentos", external_id=str(dados["id"]),
        defaults={"object_id": str(configuracao.pk), "origin": Origin.SURI,
                  "metadata": {"assinatura": assinatura,
                               "valor": str(achado[1].valor) if achado else None}})
    if achado is None:
        return f"Sem frete para o CEP {cep}: o Suri recebeu o aviso."
    return f"Orcamento enviado: {achado[0].nome} R$ {achado[1].valor} para o CEP {cep}."
