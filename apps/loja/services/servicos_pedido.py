"""Servicos do pedido editados na tela (card "Servicos do pedido" do admin).

Os servicos ficam em pedido.metadados["starhub"]["servicos"] (extras_pedido.py). A
tela manda uma linha por servico; cada linha que ja existia leva "origem" (a posicao
dela na lista gravada), a nova nao. O valor segue a regra do servico que veio da loja:

    Sofa 1500 + Montagem 80 adicionada   -> item 1580, servico "somado"
    Montagem somada removida             -> item volta a 1500
    Montagem somada de 80 para 100       -> item + 20
    Garantia so informada (sem "somado") -> muda o servico, o item nao

Servico automatico (servicos_automaticos.py) que a tela altera vira escolha do
operador; o removido volta na proxima importacao enquanto a regra do servico o incluir.
"""

import hashlib
import json
from collections import defaultdict

from django.db import transaction

from apps.loja.dinheiro import ZERO, ValorInvalido, dinheiro
from apps.loja.models import Pedido, Servico
from apps.loja.services.extras_pedido import extras, mesclar_extras
from apps.loja.totais import recalcular_totais


class ServicoInvalido(ValueError):
    pass


class ServicosMudaram(Exception):
    """Os servicos mudaram (webhook, outra aba) depois que a tela foi aberta."""


def _atuais(pedido):
    return extras(pedido).get("servicos") or []


def versao(pedido):
    texto = json.dumps(_atuais(pedido), sort_keys=True, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()


def linhas_da_tela(pedido):
    # Item que saiu do pedido vira vazio: a tela obriga a ligar de novo (ver _novo).
    itens = set(pedido.itens.values_list("pk", flat=True)) if pedido.pk else set()
    return [{"origem": posicao,
             "item_id": str(s["item_id"]) if s.get("item_id") in itens else "",
             "servico_id": str(s.get("servico_id") or ""), "opcao": s.get("opcao") or "",
             "preco": s.get("preco") or "0.00"}
            for posicao, s in enumerate(_atuais(pedido)) if isinstance(s, dict)]


def _sem_automatico(servico):
    return {k: v for k, v in servico.items() if k != "automatico"}


def _numero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _novo(linha, antigo, itens, cadastros):
    item = itens.get(_numero(linha.get("item_id")))
    if item is None:
        raise ServicoInvalido("Escolha o item do pedido em cada servico.")
    servico_id = _numero(linha.get("servico_id"))
    if servico_id is None and not (antigo and antigo.get("servico")):
        raise ServicoInvalido("Escolha o servico em cada linha nova (Loja > Servicos).")
    if servico_id is not None and servico_id not in cadastros:
        raise ServicoInvalido("Servico nao encontrado; cadastre em Loja > Servicos.")
    try:
        preco = dinheiro(linha.get("preco") or "0")
    except ValorInvalido as erro:
        raise ServicoInvalido(f"Preco do servico: {erro}") from erro
    if preco < ZERO:
        raise ServicoInvalido("Preco do servico nao pode ser negativo.")
    novo = _sem_automatico(antigo or {})
    novo.update(item_id=item.pk, sku=item.sku, opcao=(linha.get("opcao") or "Sim").strip(),
                preco=f"{preco:.2f}")
    if servico_id is not None:
        novo.update(servico_id=servico_id, servico=cadastros[servico_id].nome)
    if antigo is None:
        novo["somado"] = True  # escolhido na tela: o cliente paga, entra no item
    return novo


def _valor(servico):
    return dinheiro(servico.get("preco") or "0") if servico.get("somado") else ZERO


def preparar(pedido, linhas, itens):
    """(servicos novos, {item_id: diferenca}) sem gravar; ServicoInvalido se a tela errou."""
    atuais = _atuais(pedido)
    ids = {_numero(linha.get("servico_id")) for linha in linhas} - {None}
    cadastros = {s.pk: s for s in Servico.objects.filter(pk__in=ids)}
    novos, usados, diferencas = [], set(), defaultdict(lambda: ZERO)
    for linha in linhas:
        posicao = linha.get("origem")
        antigo = None
        if isinstance(posicao, int) and 0 <= posicao < len(atuais) and posicao not in usados:
            usados.add(posicao)
            antigo = atuais[posicao] if isinstance(atuais[posicao], dict) else None
        novo = _novo(linha, antigo, itens, cadastros)
        if antigo is not None and novo == _sem_automatico(antigo):
            novos.append(antigo)  # sem mudanca: fica como estava (automatico inclusive)
            continue
        novos.append(novo)
        if antigo is not None:
            diferencas[antigo.get("item_id")] -= _valor(antigo)
        diferencas[novo["item_id"]] += _valor(novo)
    for posicao, antigo in enumerate(atuais):
        if posicao in usados:
            continue
        if not isinstance(antigo, dict):
            novos.append(antigo)  # formato que a tela nao mostra: nao some calado
        else:
            diferencas[antigo.get("item_id")] -= _valor(antigo)
    return novos, {k: v for k, v in diferencas.items() if v and k in itens}


def aplicar(pedido_id, linhas, versao_lida):
    """Grava os servicos da tela e acerta o item; ServicosMudaram se a versao nao bate."""
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        # Relido depois do lock: o webhook que gravou antes ganha, a tela recarrega.
        if versao(pedido) != versao_lida:
            raise ServicosMudaram
        itens = {i.pk: i for i in pedido.itens.select_for_update().order_by("pk")}
        novos, diferencas = preparar(pedido, linhas, itens)
        for item_id, diferenca in diferencas.items():
            item = itens[item_id]
            if item.total + diferenca < ZERO:
                raise ServicoInvalido(f"O item {item.nome} ficaria com total negativo.")
            item.subtotal += diferenca
            item.total += diferenca
            item.save(update_fields=["subtotal", "total", "updated_at"])
        if novos != _atuais(pedido):
            mesclar_extras(pedido, {"servicos": novos})
            pedido.save(update_fields=["metadados", "updated_at"])
        if diferencas:
            recalcular_totais(pedido)
    return pedido
