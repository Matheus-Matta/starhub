"""meta_data do pedido: o que e do StarHub vai para um campo so, "starhub".

Aceita os dois jeitos de enviar:

    {"key": "starhub", "value": {"entrega": {"agendamento": "2026-10-15"}}}
    {"key": "delivery_date", "value": "2026-10-15"}      # formato antigo

Os dois viram {"key": "starhub", "value": {"entrega": {"agendamento": ...}}}.
Chave que nao e conhecida fica no meta_data como veio. Os servicos EPOFW dos
itens (epofw_field_<id>) saem do item e vao para "servicos" com o item_id.
"""

import json
import re

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.services.extras_pedido import CHAVE, RECUSAS, extras, mesclar_extras, rotulo_servico
from apps.woo_api import metadados
from apps.woo_api.erros import WooErro, parametro_invalido

_ANTIGAS = {
    "_shopify_order_id": ("origem", "id"),
    "_shopify_order_number": ("origem", "numero"),
    "_shopify_name": ("origem", "nome"),
    "_shopify_order_url": ("origem", "url"),
    "_shopify_financial_status": ("origem", "status_financeiro"),
    "_shopify_updated_at": ("origem", "atualizado_em"),
    "_billing_cpf": ("cliente", "cpf"),
    "_billing_persontype": ("cliente", "tipo_pessoa"),
    "delivery_date": ("entrega", "agendamento"),
    "delivery_type": ("entrega", "tipo"),
}
# Numero e bairro ja chegam no billing/shipping: guardar de novo so duplicaria.
_NO_ENDERECO = {"_billing_number", "_billing_neighborhood",
                "_shipping_number", "_shipping_neighborhood"}
_CUPONS = "_shopify_coupon_codes"
_EPOFW = re.compile(r"^epofw_field_\d+$")


def _objeto(valor, campo):
    """Aceita o objeto ou o objeto em texto JSON (ha ERP que serializa o value)."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            valor = None
    if not isinstance(valor, dict):
        raise parametro_invalido("meta_data", f'O value de "{campo}" deve ser um objeto JSON.')
    return valor


def _preco(valor):
    bruto = str(valor if valor is not None else "0").strip()
    # "1.499,99" e o formato brasileiro, que o EPOFW usa nas opcoes.
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        return f"{dinheiro(bruto or '0'):.2f}"
    except ValorInvalido as erro:
        raise parametro_invalido("meta_data", f"Preco do servico invalido: {valor}") from erro


def servico_valido(servico):
    if not isinstance(servico, dict):
        raise parametro_invalido("meta_data", 'Cada item de "servicos" deve ser um objeto.')
    if "preco" in servico:
        servico = {**servico, "preco": _preco(servico["preco"])}
    return servico


def _cupons(valor):
    if isinstance(valor, list):
        return [str(cupom).strip() for cupom in valor if str(cupom).strip()]
    return [cupom.strip() for cupom in str(valor or "").split(",") if cupom.strip()]


def gravar_meta(pedido, meta_data):
    """Grava o meta_data do pedido (sem salvar). Secao enviada troca a gravada."""
    if not isinstance(meta_data, list):
        raise parametro_invalido("meta_data", "meta_data nao e do tipo array.")
    atual = extras(pedido)
    secoes, soltas, resto = {}, {}, []
    for item in meta_data:
        chave = item.get("key") if isinstance(item, dict) else None
        if chave == CHAVE:
            secoes.update(_objeto(item.get("value"), CHAVE))
        elif chave in _ANTIGAS:
            secao, campo = _ANTIGAS[chave]
            soltas.setdefault(secao, {})[campo] = str(item.get("value") or "")
        elif chave == _CUPONS:
            secoes["cupons"] = _cupons(item.get("value"))
        elif chave not in _NO_ENDERECO:
            resto.append(item)
    if isinstance(secoes.get("servicos"), list):
        secoes["servicos"] = [servico_valido(servico) for servico in secoes["servicos"]]
    # Chave solta e UM campo: mescla dentro da secao em vez de trocar a secao toda.
    for secao, campos in soltas.items():
        base = secoes.get(secao, atual.get(secao))
        secoes[secao] = {**(base if isinstance(base, dict) else {}), **campos}
    if "origem" in soltas:
        secoes["origem"].setdefault("canal", "shopify")
    pedido.metadados = metadados.mesclar(pedido.metadados, resto)
    if secoes:
        mesclar_extras(pedido, secoes)


def _epofw(item):
    """{"epofw_label", "epofw_value", "epofw_price"} de um meta epofw_field_<id>."""
    try:
        valor = _objeto(item.get("value"), item["key"])
    except WooErro:  # meta que nao entendemos fica intacto no item
        return None
    interno = valor.get(item["key"], valor)
    return interno if isinstance(interno, dict) and "epofw_label" in interno else None


def separar_servicos(meta_data):
    """Tira os servicos EPOFW do meta_data do item: (servicos sem item_id, resto).

    servicos e None quando a linha nao trouxe nenhum EPOFW: ai os servicos ja
    gravados do item continuam valendo.
    """
    if not isinstance(meta_data, list):
        return None, meta_data
    servicos, resto, achou = [], [], False
    for item in meta_data:
        campo = _epofw(item) if isinstance(item, dict) and _EPOFW.match(
            str(item.get("key") or "")) else None
        if campo is None:
            resto.append(item)
            continue
        achou = True
        opcao = str(campo.get("epofw_value") or "").strip()
        if opcao and opcao.casefold() not in RECUSAS:
            servicos.append({"servico": rotulo_servico(str(campo["epofw_label"])),
                             "opcao": opcao, "preco": _preco(campo.get("epofw_price"))})
    return (servicos if achou else None), resto


def gravar_servicos(pedido, por_item):
    """Troca os servicos dos itens enviados e tira os de item que nao existe mais.

    Servico de item que nao veio na requisicao fica: PUT parcial nao apaga o resto.
    """
    atuais = extras(pedido).get("servicos") or []
    ids = set(pedido.itens.values_list("pk", flat=True))
    mantidos = [s for s in atuais if s.get("item_id") in ids and s.get("item_id") not in por_item]
    novos = [servico for servicos in por_item.values() for servico in servicos]
    servicos = sorted(mantidos + novos, key=lambda s: s.get("item_id") or 0)
    if servicos == atuais:
        return False
    mesclar_extras(pedido, {"servicos": servicos})
    return True
