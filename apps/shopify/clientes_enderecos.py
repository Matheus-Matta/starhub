"""Enderecos do cliente Shopify (defaultAddress + addressesV2) -> ClienteEndereco do hub.

Cada endereco do Shopify vira um endereco de entrega do cliente, casado pelo id
dele no vinculo (entity "enderecos_cliente"): reimportar atualiza, nao duplica.
O defaultAddress e o padrao da entrega e alimenta UM endereco de cobranca por
cliente (entity "cobranca_cliente"), atualizado no lugar quando o padrao muda.

Endereco que o hub ja tinha (admin, API Woo) nao perde o posto de padrao: so os
enderecos vindos do Shopify trocam de padrao entre si.
"""

from django.core.exceptions import ValidationError

from apps.core.models import Address, ExternalReference, Origin
from apps.loja.models import ClienteEndereco
from apps.loja.services import enderecos
from apps.loja.services.clientes import endereco_do_cliente
from apps.loja.services.enderecos import COLUNAS
from apps.loja.validators import normalizar_telefone, somente_digitos
from apps.shopify.pedidos_enderecos import _bairro, _rua_e_numero

ENTREGA = ClienteEndereco.Tipo.ENTREGA
COBRANCA = ClienteEndereco.Tipo.COBRANCA
ENTIDADE_ENTREGA = "enderecos_cliente"
ENTIDADE_COBRANCA = "cobranca_cliente"


def telefone_ou_vazio(valor):
    """Cliente.save recusa telefone fora de 8 a 15 digitos: invalido fica em branco."""
    try:
        return normalizar_telefone(valor or "")
    except ValidationError:
        return ""


def id_do_endereco(valor):
    # A busca devolve "gid://shopify/MailingAddress/11?model_name=CustomerAddress" e o
    # webhook so "11": sem cortar o sufixo, o mesmo endereco teria dois vinculos.
    texto = str(valor or "").split("?", 1)[0]
    if not texto:
        return ""
    return texto if texto.startswith("gid://") else f"gid://shopify/MailingAddress/{texto}"


def _no_formato_woo(item):
    """Chave presente com "" de proposito: o que sumiu no Shopify some no hub tambem."""
    rua, numero = _rua_e_numero(item.get("address1"), "")
    woo = {
        "first_name": item.get("firstName"), "last_name": item.get("lastName"),
        "company": item.get("company"), "address_1": rua, "address_2": item.get("address2"),
        "number": numero, "neighborhood": _bairro(item.get("address2")),
        "city": item.get("city"), "state": item.get("provinceCode") or item.get("province"),
        "postcode": item.get("zip"), "country": item.get("countryCodeV2"),
        "phone": telefone_ou_vazio(item.get("phone")),
    }
    saida = {}
    for chave, valor in woo.items():
        valor = "" if valor is None else str(valor).strip()
        if chave in COLUNAS:  # o Address recusa texto maior que a coluna
            valor = valor[:Address._meta.get_field(COLUNAS[chave]).max_length]
        saida[chave] = valor
    return saida


def _chave(rua, numero, cep):
    return (rua.strip().casefold(), numero.strip(), somente_digitos(cep))


def _igual(cliente, woo):
    """Endereco de entrega do hub identico ao do Shopify (veio antes do vinculo)."""
    procurado = _chave(woo["address_1"], woo["number"], woo["postcode"])
    for endereco in Address.objects.filter(clientes__cliente=cliente, clientes__tipo=ENTREGA):
        if _chave(endereco.address_line_1, endereco.number, endereco.postal_code) == procurado:
            return endereco
    return None


def _vinculado(entidade, externo):
    referencia = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id=externo
    ).first()
    return Address.objects.filter(pk=referencia.object_id).first() if referencia else None


def _vincular(entidade, externo, endereco, externo_cliente):
    ExternalReference.objects.update_or_create(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id=externo,
        defaults={"object_id": str(endereco.pk), "external_parent_id": externo_cliente,
                  "origin": Origin.SHOPIFY},
    )


def _gravar_entrega(cliente, item, externo_cliente):
    externo = id_do_endereco(item.get("id"))
    woo = _no_formato_woo(item)
    endereco = (_vinculado(ENTIDADE_ENTREGA, externo) if externo else None) or _igual(cliente, woo)
    endereco = enderecos.aplicar(
        endereco or Address(name=ENTREGA.label, account_id=cliente.account_id), woo)
    endereco.save()
    ClienteEndereco.objects.get_or_create(cliente=cliente, endereco=endereco, tipo=ENTREGA)
    if externo:
        _vincular(ENTIDADE_ENTREGA, externo, endereco, externo_cliente)
    return endereco


def _marcar_padrao(cliente, padrao, externo_cliente):
    do_shopify = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=ENTIDADE_ENTREGA,
        external_parent_id=externo_cliente,
    ).values_list("object_id", flat=True)
    vinculos = ClienteEndereco.objects.filter(cliente=cliente, tipo=ENTREGA)
    for vinculo in vinculos.filter(endereco_id__in=list(do_shopify)).exclude(endereco=padrao):
        if vinculo.padrao:
            vinculo.padrao = False
            vinculo.save()
    vinculo = vinculos.get(endereco=padrao)
    if not vinculo.padrao:
        vinculo.padrao = True
        vinculo.save()


def _gravar_cobranca(cliente, item, externo_cliente):
    endereco = _vinculado(ENTIDADE_COBRANCA, externo_cliente)
    if endereco is None:
        if endereco_do_cliente(cliente, COBRANCA) is not None:
            return  # a cobranca que o hub (ou o ERP) cadastrou continua mandando
        endereco = Address(name=COBRANCA.label, account_id=cliente.account_id)
    novo = endereco.pk is None
    endereco = enderecos.aplicar(endereco, _no_formato_woo(item))
    endereco.save()
    if novo:
        ClienteEndereco.objects.create(cliente=cliente, endereco=endereco, tipo=COBRANCA,
                                       padrao=True)
    _vincular(ENTIDADE_COBRANCA, externo_cliente, endereco, externo_cliente)


def sincronizar_enderecos(cliente, dados):
    """Sem defaultAddress nem addressesV2 nos dados (pedido, payload parcial): nao mexe."""
    if "defaultAddress" not in dados and "addressesV2" not in dados:
        return
    externo_cliente = dados["id"]
    padrao = dados.get("defaultAddress") or None
    itens = list((dados.get("addressesV2") or {}).get("nodes") or [])
    id_padrao = id_do_endereco((padrao or {}).get("id"))
    if padrao and id_padrao not in {id_do_endereco(item.get("id")) for item in itens}:
        itens.append(padrao)
    gravados = {}
    for item in itens:
        gravados[id_do_endereco(item.get("id"))] = _gravar_entrega(cliente, item, externo_cliente)
    if padrao:
        _marcar_padrao(cliente, gravados[id_padrao], externo_cliente)
        _gravar_cobranca(cliente, padrao, externo_cliente)
    # O prefetch (se houver) ficou velho: a proxima leitura busca de novo.
    getattr(cliente, "_prefetched_objects_cache", {}).pop("vinculos_endereco", None)
