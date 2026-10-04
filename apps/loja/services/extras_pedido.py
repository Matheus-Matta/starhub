"""Extras do pedido (origem, agendamento, servicos...) num metadado so: "starhub".

Os metadados seguem a lista do Woo ({"id", "key", "value"}). Espalhar cada dado
numa chave propria (_billing_cpf, delivery_date...) deixa o ERP e a tela caçando
chave; aqui tudo fica num objeto, separado por secao:

    mesclar_extras(pedido, {"entrega": {"agendamento": "2026-10-15"}})
    extras(pedido) -> {"origem": {...}, "entrega": {"agendamento": "2026-10-15"}}

Nao salva o pedido: quem chama salva.
"""

import re

CHAVE = "starhub"
# Opcao que diz "nao quero o servico": nao e servico contratado.
RECUSAS = {"não", "nao", "no", "false"}
# Rotulos que a loja escreve de varios jeitos; o resto vem do nome do campo.
_ROTULOS = (
    ("imper", "Impermeabilização da poltrona"),
    ("montagem", "Montagem"),
    ("garantia", "Garantia estendida"),
)


def _vazio(valor):
    return valor is None or valor == "" or valor == [] or valor == {}


def _limpo(valor):
    """Campo sem valor fica fora: o ERP nao precisa distinguir "" de ausente."""
    if isinstance(valor, dict):
        return {chave: _limpo(v) for chave, v in valor.items() if not _vazio(_limpo(v))}
    if isinstance(valor, list):
        return [_limpo(v) for v in valor if not _vazio(_limpo(v))]
    return valor


def definir_meta(lista, chave, valor):
    """Grava `chave` numa lista de metadados do Woo, trocando o valor se ja existir."""
    lista = [dict(item) for item in (lista or [])]
    alvo = next((item for item in lista if item.get("key") == chave), None)
    if alvo is None:
        proximo = max((item.get("id", 0) for item in lista), default=0) + 1
        lista.append({"id": proximo, "key": chave, "value": valor})
    else:
        alvo["value"] = valor
    return lista


def ler_meta(lista, chave, padrao=None):
    item = next((item for item in (lista or []) if item.get("key") == chave), None)
    return padrao if item is None else item.get("value")


def extras(pedido):
    valor = ler_meta(pedido.metadados, CHAVE)
    return dict(valor) if isinstance(valor, dict) else {}


def mesclar_extras(pedido, secoes):
    """Troca so as secoes enviadas; secao vazia e removida."""
    atual = extras(pedido)
    for secao, valor in secoes.items():
        valor = _limpo(valor)
        if _vazio(valor):
            atual.pop(secao, None)
        else:
            atual[secao] = valor
    pedido.metadados = definir_meta(pedido.metadados, CHAVE, atual)
    return atual


def rotulo_servico(nome):
    """Nome do servico para gente ler: "_montagem_456" e "MONTAGEM:" viram "Montagem".

    Fica aqui porque o Shopify (propriedade do item) e o ERP (campo EPOFW) mandam
    o mesmo servico com nomes diferentes, e os dois tem que cair no mesmo rotulo.
    """
    minusculo = nome.casefold()
    for trecho, rotulo in _ROTULOS:
        if trecho in minusculo:
            return rotulo
    limpo = re.sub(r"_\d+$", "", nome.strip().strip("_")).replace("_", " ").strip(" :")
    return limpo[:1].upper() + limpo[1:].lower()
