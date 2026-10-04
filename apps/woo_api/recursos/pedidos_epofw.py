"""Servicos do item no formato do plugin EPOFW, como o Woo real devolve.

O ERP foi feito para uma loja Woo com o EPOFW e le o servico de
line_items[].meta_data[].key == "epofw_field_<n>". O value vai como texto JSON,
igual ao que o Woo grava:

    {"key": "epofw_field_1", "value": "{\"epofw_field_1\": {\"epofw_label\":
        \"IMPERMEABILIZAÇÃO DA POLTRONA:\", \"epofw_value\": \"Sim\", ...}}"}

E montado na hora a partir dos servicos do pedido (a fonte unica). Na volta,
pedidos_meta.separar_servicos le esse mesmo formato, entao o ERP pode reenviar
o que recebeu sem mudar nem duplicar o servico.
"""

import json

from apps.loja.services.extras_pedido import RECUSAS


def _virgula(preco):
    """O EPOFW escreve o preco das opcoes no formato brasileiro: "499,99"."""
    return str(preco).replace(".", ",")


def _campo(numero, item, servico):
    nome = f"epofw_field_{numero}"
    rotulo = f"{str(servico.get('servico') or '').upper()}:"
    opcao = str(servico.get("opcao") or "")
    preco = str(servico.get("preco") or "0.00")
    opcoes = {opcao: f"{opcao}||fixed||{_virgula(preco)}"}
    # O radiogroup do EPOFW sempre tem a recusa; o ERP pode montar a tela por ele.
    if opcao.casefold() not in RECUSAS:
        opcoes["Não"] = "Não||fixed||0,00"
    return {
        "epofw_field_quantity": str(item.quantidade),
        "epofw_label": rotulo,
        "product_id": str(item.produto_id or 0),
        "epofw_type": "radiogroup",
        "epofw_name": nome,
        "epofw_value": opcao,
        "epofw_price": preco,
        "epofw_original_price": preco,
        "epofw_price_type": "fixed",
        "epofw_form_data": {
            "field_status": "on",
            "field": {"type": "radiogroup", "name": str(numero), "id": str(numero),
                      "class": str(numero)},
            "label": {"title": rotulo, "class": f"epofw_label_{numero}",
                      "subtitle": "", "subtitle_class": ""},
            "epofw_field_settings": {"options": opcoes},
        },
    }


def metas_epofw(item, servicos, primeiro_id):
    """Um epofw_field_<n> por servico; ids de meta a partir de primeiro_id."""
    saida = []
    for numero, servico in enumerate(servicos or [], start=1):
        nome = f"epofw_field_{numero}"
        valor = {nome: _campo(numero, item, servico)}
        saida.append({"id": primeiro_id + numero - 1, "key": nome,
                      "value": json.dumps(valor, ensure_ascii=False)})
    return saida
