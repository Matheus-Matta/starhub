"""Servicos do hub no Suri Shop, que nao tem servico: cada um vira variante do produto.

    Sofa (Cor: Azul, Cor: Verde) + Montagem (regra em Loja > Servicos)
    -> attributes: [..., {"name": "Serviços", "options": [{"name": "Montagem"}]}]
    -> dimensions: [..., {"sku": "SERV-MONTAGEM", "dimensions": {"Serviços": "Montagem"},
                          "price": <preco da regra>, "stocks": {...},
                          "image": {"url": <foto do servico>, "description": "Montagem"}}]

A dimension tem "image" propria (doc do Suri, Postman "Criar Produto"); sem foto no
servico, a chave nem vai.

So com Integracoes > Suri > "enviar servicos como variantes" ligado. O PUT do Suri
troca o produto inteiro: produto que saiu da regra vai sem a variante e ela some la.
O vinculo "servicos" ("<produto>:<sku>" -> Servico, pai = produto) diz o que foi;
e dele que sai o reenvio quando a regra muda (servicos_sinais.py) e o servico do
pedido que chega (importar_itens.py, com "receber servicos" ligado).
"""

from apps.core.models import ExternalReference
from apps.integracoes.url_publica import url_publica
from apps.loja.models import Servico
from apps.suri import vinculos

ATRIBUTO = "Serviços"
# "Servico" foi o nome ate a 1.3.18: o produto la ainda pode ter, e a importacao o ignora.
ATRIBUTOS = {ATRIBUTO, "Servico"}
ENTIDADE = "servicos"


def do_produto(configuracao, produto):
    """[(servico, preco)] que vao como variante; vazio com o envio desligado."""
    if not getattr(configuracao, "enviar_servicos", False):
        return []
    return produto.servicos


def _foto(configuracao, servico):
    imagem = servico.imagem if isinstance(servico.imagem, dict) else {}
    url = url_publica(configuracao, imagem.get("src"))
    return {"url": url, "description": imagem.get("alt") or servico.nome} if url else None


def dimensoes(servicos, variantes, loja, skus_do_produto, configuracao=None):
    """Uma dimensao por servico. SKU igual ao de uma variante do produto fica de fora:
    o Suri teria dois itens com o mesmo SKU e o estoque iria para o errado."""
    # O servico nao tem estoque: vende enquanto o produto tiver.
    estoque = sum(max(v.inventory_quantity, 0) for v in variantes)
    saida = []
    for servico, preco in servicos:
        if servico.sku in skus_do_produto:
            continue
        dimensao = {"sku": servico.sku, "dimensions": {ATRIBUTO: servico.nome},
                    "price": preco, "stocks": {loja: {"stock": estoque}}}
        foto = _foto(configuracao, servico) if configuracao else None
        if foto:
            dimensao["image"] = foto
        saida.append(dimensao)
    return saida


def _do_produto_no_suri(produto_id):
    return ExternalReference.objects.filter(
        platform=vinculos.PLATAFORMA, entity_type=ENTIDADE, external_parent_id=str(produto_id))


def vincular(produto_id, servicos, dados):
    """Grava o que foi como variante e apaga o vinculo do que saiu do produto."""
    enviados = {d["sku"] for d in dados["dimensions"]}
    chaves = []
    for servico, _preco in servicos:
        if servico.sku in enviados:
            chave = vinculos.id_variacao(produto_id, servico.sku)
            vinculos.referenciar(ENTIDADE, chave, servico, pai=produto_id)
            chaves.append(chave)
    _do_produto_no_suri(produto_id).exclude(external_id__in=chaves).delete()


def desvincular(produto_id):
    _do_produto_no_suri(produto_id).delete()


def produtos_no_suri(servico_id):
    """Ids no Suri dos produtos que levam o servico como variante hoje."""
    return set(ExternalReference.objects.filter(
        platform=vinculos.PLATAFORMA, entity_type=ENTIDADE, object_id=str(servico_id))
        .values_list("external_parent_id", flat=True))


def da_linha(linha):
    """Servico do item do pedido do Suri: pelo vinculo da variante, depois pelo SKU."""
    produto_id, sku = str(linha.get("providerId") or ""), str(linha.get("sku") or "").strip()
    if not sku:
        return None
    servico = vinculos.existente(ENTIDADE, Servico, vinculos.id_variacao(produto_id, sku))
    return servico or Servico.objects.filter(sku=sku).first()
